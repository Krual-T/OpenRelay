from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from openrelay.backends.base import BackendContext
from openrelay.backends.codex import CodexAppServerClient
from openrelay.models import SessionRecord, utc_now


class DummyStdin:
    def write(self, _data: bytes) -> None:
        return None

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None


class DummyProcess:
    def __init__(self) -> None:
        self.stdin = DummyStdin()
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.terminated = True

    async def wait(self) -> int:
        return 0


def make_session(tmp_path: Path) -> SessionRecord:
    return SessionRecord(
        session_id="s_test",
        base_key="test",
        backend="codex",
        cwd=str(tmp_path),
        label="test",
        model_override="",
        safety_mode="danger-full-access",
        native_session_id="",
        release_channel="main",
        created_at=utc_now(),
    )


@pytest.mark.asyncio
async def test_codex_request_timeout_resets_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = CodexAppServerClient(
        codex_path="codex",
        workspace_root=tmp_path,
        sqlite_home=tmp_path / "codex-state",
        model="gpt-test",
        safety_mode="danger-full-access",
        request_timeout_seconds=0.01,
        interrupt_grace_seconds=0.01,
    )
    client.process = DummyProcess()

    async def fake_ensure_ready() -> None:
        return None

    reset_reasons: list[str] = []

    async def fake_reset(reason: str) -> None:
        reset_reasons.append(reason)

    monkeypatch.setattr(client, "ensure_ready", fake_ensure_ready)
    monkeypatch.setattr(client, "_reset", fake_reset)

    with pytest.raises(RuntimeError, match="request turn/start timed out"):
        await client.request("turn/start", {"threadId": "t_1"})

    assert reset_reasons == ["Codex app-server request turn/start timed out after 0.01s"]
    assert client.pending_requests == {}


@pytest.mark.asyncio
async def test_codex_request_has_no_default_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = CodexAppServerClient(
        codex_path="codex",
        workspace_root=tmp_path,
        sqlite_home=tmp_path / "codex-state",
        model="gpt-test",
        safety_mode="danger-full-access",
        request_timeout_seconds=None,
        interrupt_grace_seconds=0.01,
    )
    client.process = DummyProcess()

    async def fake_ensure_ready() -> None:
        return None

    monkeypatch.setattr(client, "ensure_ready", fake_ensure_ready)

    task = asyncio.create_task(client.request("turn/start", {"threadId": "t_1"}))

    while not client.pending_requests:
        await asyncio.sleep(0)
    await asyncio.sleep(0.02)

    assert not task.done()

    request_id = next(iter(client.pending_requests))
    await client._handle_message({"id": request_id, "result": {"turn": {"id": "turn_1"}}})

    assert await task == {"turn": {"id": "turn_1"}}
    assert client.pending_requests == {}


@pytest.mark.asyncio
async def test_codex_interrupt_timeout_forces_reset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = CodexAppServerClient(
        codex_path="codex",
        workspace_root=tmp_path,
        sqlite_home=tmp_path / "codex-state",
        model="gpt-test",
        safety_mode="danger-full-access",
        request_timeout_seconds=1,
        interrupt_grace_seconds=0.01,
    )
    session = make_session(tmp_path)
    interrupt_calls: list[dict[str, object]] = []
    reset_reasons: list[str] = []

    async def fake_ensure_thread(_session: SessionRecord, _context: BackendContext) -> str:
        return "thread_1"

    async def fake_request(method: str, params: dict[str, object], **_kwargs: object) -> dict[str, object]:
        if method == "turn/start":
            return {"turn": {"id": "turn_1"}}
        if method == "turn/interrupt":
            interrupt_calls.append(params)
            return {}
        raise AssertionError(f"unexpected request: {method}")

    async def fake_reset(reason: str) -> None:
        reset_reasons.append(reason)
        for turn in list(client.active_turns):
            if turn.future is not None and not turn.future.done():
                turn.future.set_exception(RuntimeError(reason))

    monkeypatch.setattr(client, "ensure_thread", fake_ensure_thread)
    monkeypatch.setattr(client, "request", fake_request)
    monkeypatch.setattr(client, "_reset", fake_reset)

    cancel_event = asyncio.Event()
    task = asyncio.create_task(
        client.run_turn(
            session,
            "hello",
            BackendContext(workspace_root=tmp_path, cancel_event=cancel_event),
        )
    )
    await asyncio.sleep(0)
    cancel_event.set()

    with pytest.raises(RuntimeError, match="did not stop after interrupt"):
        await task

    assert interrupt_calls == [{"threadId": "thread_1", "turnId": "turn_1"}]
    assert reset_reasons == ["Codex app-server did not stop after interrupt within 0.01s"]


@pytest.mark.asyncio
async def test_codex_turn_start_cancel_before_response_resets_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = CodexAppServerClient(
        codex_path="codex",
        workspace_root=tmp_path,
        sqlite_home=tmp_path / "codex-state",
        model="gpt-test",
        safety_mode="danger-full-access",
        request_timeout_seconds=1,
        interrupt_grace_seconds=0.01,
    )
    client.process = DummyProcess()
    session = make_session(tmp_path)
    reset_reasons: list[str] = []

    async def fake_ensure_ready() -> None:
        return None

    async def fake_ensure_thread(_session: SessionRecord, _context: BackendContext) -> str:
        return "thread_1"

    async def fake_reset(reason: str) -> None:
        reset_reasons.append(reason)
        for future in list(client.pending_requests.values()):
            if not future.done():
                future.cancel()
        client.pending_requests.clear()
        for turn in list(client.active_turns):
            if turn.future is not None and not turn.future.done():
                turn.future.cancel()

    monkeypatch.setattr(client, "ensure_ready", fake_ensure_ready)
    monkeypatch.setattr(client, "ensure_thread", fake_ensure_thread)
    monkeypatch.setattr(client, "_reset", fake_reset)

    cancel_event = asyncio.Event()
    task = asyncio.create_task(
        client.run_turn(
            session,
            "hello",
            BackendContext(workspace_root=tmp_path, cancel_event=cancel_event),
        )
    )

    while not client.pending_requests:
        await asyncio.sleep(0)
    cancel_event.set()

    with pytest.raises(RuntimeError, match="interrupted by /stop"):
        await task

    assert reset_reasons == ["Codex app-server request turn/start cancelled by /stop before response"]
    assert client.pending_requests == {}


@pytest.mark.asyncio
async def test_codex_resume_timeout_falls_back_to_fresh_thread(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = CodexAppServerClient(
        codex_path="codex",
        workspace_root=tmp_path,
        sqlite_home=tmp_path / "codex-state",
        model="gpt-test",
        safety_mode="danger-full-access",
        resume_timeout_seconds=0.01,
    )
    session = make_session(tmp_path)
    session.native_session_id = "thread_stale"
    called: list[str] = []
    reset_reasons: list[str] = []

    async def fake_ensure_ready() -> None:
        return None

    async def fake_request(method: str, params: dict[str, object], **_kwargs: object) -> dict[str, object]:
        called.append(method)
        if method == "thread/resume":
            await asyncio.sleep(0.05)
            return {}
        if method == "thread/start":
            return {"thread": {"id": "thread_fresh"}}
        raise AssertionError(f"unexpected request: {method}")

    async def fake_reset(reason: str) -> None:
        reset_reasons.append(reason)

    monkeypatch.setattr(client, "ensure_ready", fake_ensure_ready)
    monkeypatch.setattr(client, "request", fake_request)
    monkeypatch.setattr(client, "_reset", fake_reset)

    thread_id = await client.ensure_thread(session, BackendContext(workspace_root=tmp_path))

    assert thread_id == "thread_fresh"
    assert called == ["thread/resume", "thread/start"]
    assert reset_reasons == ["Codex app-server thread/resume timed out after 0.01s"]


def test_codex_process_env_overrides_sqlite_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-from-parent")
    client = CodexAppServerClient(
        codex_path="codex",
        workspace_root=tmp_path,
        sqlite_home=tmp_path / "codex-state",
        model="gpt-test",
        safety_mode="danger-full-access",
    )

    env = client._build_process_env()

    assert env["CODEX_SQLITE_HOME"] == str((tmp_path / "codex-state").resolve())
    assert env["CODEX_THREAD_ID"] == "thread-from-parent"
