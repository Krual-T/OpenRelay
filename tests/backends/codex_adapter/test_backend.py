from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from openrelay.agent_runtime import (
    ApprovalDecision,
    ApprovalRequestedEvent,
    ListSessionsRequest,
    RuntimeEvent,
    SessionLocator,
    SessionStartedEvent,
    StartSessionRequest,
    TurnCompletedEvent,
    TurnInput,
)
from openrelay.backends.codex_adapter.backend import CodexRuntimeBackend


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
        self.compaction_item_count = 0
        self.compact_notifies = True

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
        if method == "thread/read":
            turns = [{"items": [{"id": f"compact_{index}", "type": "contextCompaction"} for index in range(self.compaction_item_count)]}]
            return {
                "thread": {
                    "id": str(params.get("threadId") or ""),
                    "preview": "preview",
                    "cwd": str(self.workspace_root),
                    "updatedAt": "2026-03-16T00:00:00Z",
                    "status": {"type": "idle"},
                    "name": "Thread 1",
                    "turns": turns,
                }
            }
        if method == "thread/compact/start":
            self.compaction_item_count += 1
            if self.compact_notifies:
                for subscriber in list(self.active_turns):
                    await subscriber.handle_notification(
                        self,
                        "thread/compacted",
                        {"threadId": str(params.get("threadId") or ""), "turnId": "turn_compact_1"},
                    )
            return {"threadId": str(params.get("threadId") or ""), "compactId": "compact_1", "status": "started"}
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
    assert compact == {
        "threadId": "thread_1",
        "compactId": "compact_1",
        "status": "completed",
        "completionSource": "notification",
        "turnId": "turn_compact_1",
    }


@pytest.mark.asyncio
async def test_codex_runtime_backend_waits_for_compact_via_thread_read_polling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class PollingCompactClient(FakeCodexClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self.compact_notifies = False

    monkeypatch.setattr("openrelay.backends.codex_adapter.transport.CodexAppServerClient", PollingCompactClient)
    backend = CodexRuntimeBackend(
        codex_path="codex",
        default_model="gpt-test",
        workspace_root=tmp_path,
        sqlite_home=tmp_path / "sqlite",
    )

    compact = await backend.compact_session(SessionLocator(backend="codex", native_session_id="thread_1"))

    assert compact == {
        "threadId": "thread_1",
        "compactId": "compact_1",
        "status": "completed",
        "completionSource": "thread_read",
    }


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
