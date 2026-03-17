from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from openrelay.agent_runtime import (
    RateLimitsUpdatedEvent,
    ApprovalDecision,
    ApprovalRequestedEvent,
    SkillsUpdatedEvent,
    ThreadDiffUpdatedEvent,
    ThreadStatusUpdatedEvent,
    ListSessionsRequest,
    RuntimeEvent,
    SessionLocator,
    SessionStartedEvent,
    StartSessionRequest,
    TurnCompletedEvent,
    TurnInput,
)
from openrelay.backends.codex_adapter.backend import CodexRuntimeBackend
from openrelay.backends.codex_adapter.app_server import CodexTurn


class FakeCodexClient:
    def __init__(
        self,
        codex_path: str,
        workspace_root: Path,
        sqlite_home: Path,
        model: str,
        safety_mode: str,
        **_: object,
    ) -> None:
        self.codex_path = codex_path
        self.workspace_root = workspace_root
        self.sqlite_home = sqlite_home
        self.model = model
        self.safety_mode = safety_mode
        self.active_turns: set[object] = set()
        self.sent_server_results: list[tuple[int | str, dict[str, object]]] = []
        self.started = 0

    async def request(self, method: str, params: dict[str, object], **_: object) -> dict[str, object]:
        if method == "thread/start":
            self.started += 1
            return {"thread": {"id": f"thread_{self.started}", "preview": "preview", "updatedAt": "2026-03-16T00:00:00Z", "status": "idle"}}
        if method == "thread/resume":
            return {"thread": {"id": str(params.get("threadId") or "")}}
        if method == "turn/start":
            turn = next(iter(self.active_turns))
            await turn.handle_notification(
                self,
                "turn/started",
                {"threadId": "thread_1", "turn": {"id": "turn_1"}},
            )
            await turn.handle_notification(
                self,
                "item/agentMessage/delta",
                {"threadId": "thread_1", "turnId": "turn_1", "itemId": "msg_1", "delta": "hello"},
            )
            await turn.handle_notification(
                self,
                "turn/completed",
                {"threadId": "thread_1", "turnId": "turn_1", "turn": {"status": "completed"}},
            )
            return {"turn": {"id": "turn_1"}}
        if method == "turn/interrupt":
            return {}
        raise AssertionError(f"unexpected request: {method}")

    async def list_threads(self, limit: int = 20) -> tuple[list[object], str]:
        _ = limit
        summary = type("Summary", (), {"thread_id": "thread_1", "preview": "preview", "cwd": str(self.workspace_root), "updated_at": "2026-03-16T00:00:00Z", "status": "idle", "name": "Thread 1"})
        return ([summary], "")

    async def read_thread(self, thread_id: str, *, include_turns: bool = True) -> object:
        _ = include_turns
        message = type("Message", (), {"role": "assistant", "text": f"from {thread_id}"})
        return type(
            "Details",
            (),
            {
                "thread_id": thread_id,
                "preview": "preview",
                "cwd": str(self.workspace_root),
                "updated_at": "2026-03-16T00:00:00Z",
                "status": "idle",
                "name": "Thread 1",
                "messages": (message,),
            },
        )

    async def compact_thread(self, thread_id: str) -> dict[str, object]:
        return {"threadId": thread_id, "status": "started"}

    async def _send_server_result(self, request_id: int | str, result: dict[str, object]) -> None:
        self.sent_server_results.append((request_id, result))

    async def shutdown(self) -> None:
        return


class CapturingSink:
    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []

    async def publish(self, event: RuntimeEvent) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_codex_app_server_turn_emits_legacy_progress_for_system_runtime_events() -> None:
    progress_events: list[dict[str, object]] = []

    async def capture(event: dict[str, object]) -> None:
        progress_events.append(event)

    turn = CodexTurn(thread_id="thread_1", on_progress=capture)

    await turn._apply_runtime_event(
        ThreadStatusUpdatedEvent(
            backend="codex",
            session_id="thread_1",
            turn_id="turn_1",
            event_type="thread.status.updated",
            status="active",
        )
    )
    await turn._apply_runtime_event(
        RateLimitsUpdatedEvent(
            backend="codex",
            session_id="thread_1",
            turn_id="turn_1",
            event_type="rate_limits.updated",
            rate_limits={"limitId": "codex", "primary": {"usedPercent": 37}},
        )
    )
    await turn._apply_runtime_event(
        SkillsUpdatedEvent(
            backend="codex",
            session_id="thread_1",
            turn_id="turn_1",
            event_type="skills.updated",
            version="skills-v3",
            skills=("search", "apply_patch"),
        )
    )
    await turn._apply_runtime_event(
        ThreadDiffUpdatedEvent(
            backend="codex",
            session_id="thread_1",
            turn_id="turn_1",
            event_type="thread.diff.updated",
            diff_id="diff_9",
        )
    )

    assert progress_events == [
        {"type": "thread.status", "status": "active", "threadId": "thread_1"},
        {"type": "rate_limits.updated", "rateLimits": {"limitId": "codex", "primary": {"usedPercent": 37}}, "threadId": "thread_1"},
        {"type": "skills.updated", "version": "skills-v3", "skills": ["search", "apply_patch"], "threadId": "thread_1"},
        {"type": "thread.diff.updated", "diffId": "diff_9", "threadId": "thread_1"},
    ]


@pytest.mark.asyncio
async def test_codex_runtime_backend_starts_session_and_reads_threads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("openrelay.backends.codex_adapter.transport.CodexAppServerClient", FakeCodexClient)
    backend = CodexRuntimeBackend(
        codex_path="codex",
        default_model="gpt-test",
        workspace_root=tmp_path,
        sqlite_home=tmp_path / "sqlite",
    )

    summary = await backend.start_session(
        StartSessionRequest(cwd=str(tmp_path), model="gpt-test", safety_mode="workspace-write")
    )
    sessions, cursor = await backend.list_sessions(ListSessionsRequest(limit=20, cwd=str(tmp_path)))
    transcript = await backend.read_session(SessionLocator(backend="codex", native_session_id="thread_1"))
    compact = await backend.compact_session(SessionLocator(backend="codex", native_session_id="thread_1"))

    assert summary.native_session_id == "thread_1"
    assert sessions[0].native_session_id == "thread_1"
    assert cursor == ""
    assert transcript.messages[0].text == "from thread_1"
    assert compact == {"threadId": "thread_1", "status": "started"}


@pytest.mark.asyncio
async def test_codex_runtime_backend_streams_runtime_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("openrelay.backends.codex_adapter.transport.CodexAppServerClient", FakeCodexClient)
    backend = CodexRuntimeBackend(
        codex_path="codex",
        default_model="gpt-test",
        workspace_root=tmp_path,
        sqlite_home=tmp_path / "sqlite",
    )
    sink = CapturingSink()

    handle = await backend.start_turn(
        SessionLocator(backend="codex", native_session_id=""),
        TurnInput(
            text="hello",
            cwd=str(tmp_path),
            model="gpt-test",
            metadata={"relay_session_id": "relay_1"},
        ),
        sink,
    )
    await handle.wait()

    assert handle.turn_id == "turn_1"
    assert any(isinstance(event, SessionStartedEvent) for event in sink.events)
    assert any(event.event_type == "assistant.delta" for event in sink.events)
    assert any(isinstance(event, TurnCompletedEvent) for event in sink.events)


class FakeApprovalClient(FakeCodexClient):
    async def request(self, method: str, params: dict[str, object], **_: object) -> dict[str, object]:
        if method == "thread/resume":
            return {"thread": {"id": str(params.get("threadId") or "")}}
        if method == "turn/start":
            turn = next(iter(self.active_turns))
            asyncio.create_task(
                turn.handle_server_request(
                    self,
                    7,
                    "item/commandExecution/requestApproval",
                    {
                        "threadId": "thread_1",
                        "turnId": "turn_1",
                        "command": "pytest -q",
                        "cwd": str(self.workspace_root),
                    },
                )
            )
            return {"turn": {"id": "turn_1"}}
        return await super().request(method, params, **_)


@pytest.mark.asyncio
async def test_codex_runtime_backend_resolves_pending_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("openrelay.backends.codex_adapter.transport.CodexAppServerClient", FakeApprovalClient)
    backend = CodexRuntimeBackend(
        codex_path="codex",
        default_model="gpt-test",
        workspace_root=tmp_path,
        sqlite_home=tmp_path / "sqlite",
    )
    sink = CapturingSink()
    locator = SessionLocator(backend="codex", native_session_id="thread_1")

    handle = await backend.start_turn(
        locator,
        TurnInput(
            text="hello",
            cwd=str(tmp_path),
            model="gpt-test",
            metadata={"relay_session_id": "relay_1"},
        ),
        sink,
    )

    for _ in range(20):
        requests = [event for event in sink.events if isinstance(event, ApprovalRequestedEvent)]
        if requests:
            break
        await asyncio.sleep(0)
    assert requests

    await backend.resolve_approval(
        locator,
        ApprovalDecision(decision="accept_for_session"),
        requests[0].request,
    )

    for _ in range(20):
        client = next(iter(backend._clients.values())).transport._client
        if client is not None and client.sent_server_results:
            break
        await asyncio.sleep(0)
    client = next(iter(backend._clients.values())).transport._client

    assert client is not None
    assert client.sent_server_results == [(7, {"decision": "acceptForSession"})]
    assert not handle.future.done()
