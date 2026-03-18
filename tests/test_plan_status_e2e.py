from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.backends.codex_adapter.backend import CodexRuntimeBackend
from openrelay.core import BackendReply, IncomingMessage, SessionRecord
from openrelay.runtime.turn import BackendTurnSession, TurnRuntimeContext
from openrelay.session import RelaySessionBinding


class FakePlanStatusClient:
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
        self.started = 0

    async def request(self, method: str, params: dict[str, object], **_: object) -> dict[str, object]:
        if method == "thread/start":
            self.started += 1
            return {"thread": {"id": f"thread_{self.started}", "preview": "preview", "updatedAt": "2026-03-18T00:00:00Z", "status": "idle"}}
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
                "turn/plan/updated",
                {
                    "threadId": "thread_1",
                    "turnId": "turn_1",
                    "plan": [
                        {"step": "Inspect runtime", "status": "completed"},
                        {"step": "Wire mapper", "status": "inProgress"},
                    ],
                    "explanation": "phase 1",
                },
            )
            await turn.handle_notification(
                self,
                "item/agentMessage/delta",
                {"threadId": "thread_1", "turnId": "turn_1", "itemId": "msg_1", "delta": "Final answer"},
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
        return ([], "")

    async def read_thread(self, thread_id: str, *, include_turns: bool = True) -> object:
        _ = thread_id, include_turns
        return object()

    async def _send_server_result(self, request_id: int | str, result: dict[str, object]) -> None:
        _ = request_id, result

    async def shutdown(self) -> None:
        return


class InMemoryBindingStore:
    def __init__(self) -> None:
        self.bindings: dict[str, RelaySessionBinding] = {}

    def save(self, binding: RelaySessionBinding) -> None:
        self.bindings[binding.relay_session_id] = binding

    def get(self, relay_session_id: str) -> RelaySessionBinding | None:
        return self.bindings.get(relay_session_id)

    def update_native_session_id(self, relay_session_id: str, native_session_id: str) -> None:
        binding = self.bindings.get(relay_session_id)
        if binding is None:
            return
        self.bindings[relay_session_id] = RelaySessionBinding(
            relay_session_id=binding.relay_session_id,
            backend=binding.backend,
            native_session_id=native_session_id,
            cwd=binding.cwd,
            model=binding.model,
            safety_mode=binding.safety_mode,
            feishu_chat_id=binding.feishu_chat_id,
            feishu_thread_id=binding.feishu_thread_id,
            created_at=binding.created_at,
            updated_at=binding.updated_at,
        )


class FakeStore:
    def __init__(self, session: SessionRecord) -> None:
        self.session = session
        self.messages: list[tuple[str, str, str]] = []

    def save_session(self, session: SessionRecord) -> SessionRecord:
        self.session = session
        return session

    def append_message(self, session_id: str, role: str, content: str) -> None:
        self.messages.append((session_id, role, content))


class FakeTypingManager:
    async def add(self, message_id: str) -> dict[str, str]:
        return {"message_id": message_id}

    async def remove(self, state: dict[str, str]) -> None:
        _ = state


class FakeStreamingSession:
    def __init__(self) -> None:
        self.started = False
        self.active = False
        self.updates: list[dict[str, Any]] = []
        self.final_card: dict[str, Any] | None = None
        self.started_route: dict[str, str] | None = None

    async def start(self, receive_id: str, *, reply_to_message_id: str = "", root_id: str = "") -> None:
        self.started = True
        self.active = True
        self.started_route = {
            "receive_id": receive_id,
            "reply_to_message_id": reply_to_message_id,
            "root_id": root_id,
        }

    def has_started(self) -> bool:
        return self.started

    def is_active(self) -> bool:
        return self.active

    def needs_rollover(self) -> bool:
        return False

    def message_id(self) -> str:
        return "om_stream"

    def message_alias_ids(self) -> tuple[str, ...]:
        return ("om_stream",)

    async def update(self, snapshot: dict[str, Any]) -> None:
        self.updates.append(snapshot)

    async def freeze(self, live_state: dict[str, Any], *, notice_text: str = "") -> None:
        _ = live_state, notice_text

    async def close(self, final_card: dict[str, Any] | None = None) -> None:
        self.active = False
        self.final_card = final_card


def _build_message() -> IncomingMessage:
    return IncomingMessage(
        event_id="evt_plan",
        message_id="om_input",
        chat_id="oc_test",
        chat_type="p2p",
        sender_open_id="ou_user",
        text="trace plan status",
        actionable=True,
    )


def _build_session(tmp_path: Path) -> SessionRecord:
    return SessionRecord(
        session_id="relay_1",
        base_key="base_1",
        backend="codex",
        cwd=str(tmp_path),
        safety_mode="workspace-write",
    )


def _extract_markdown_blocks(card: dict[str, Any] | None) -> list[str]:
    blocks: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        content = node.get("content")
        if isinstance(content, str) and content.strip():
            blocks.append(content)
        for value in node.values():
            walk(value)

    walk(card or {})
    return blocks


@pytest.mark.asyncio
async def test_e2e_plan_status_trace_reaches_feishu_final_card(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr("openrelay.backends.codex_adapter.transport.CodexAppServerClient", FakePlanStatusClient)
    caplog.set_level(logging.INFO)

    backend = CodexRuntimeBackend(
        codex_path="codex",
        default_model="gpt-test",
        workspace_root=tmp_path,
        sqlite_home=tmp_path / "sqlite",
    )
    binding_store = InMemoryBindingStore()
    runtime_service = AgentRuntimeService({"codex": backend}, binding_store)  # type: ignore[arg-type]

    session = _build_session(tmp_path)
    store = FakeStore(session)
    streaming = FakeStreamingSession()
    final_replies: list[BackendReply] = []

    async def reply_final(
        message: IncomingMessage,
        text: str,
        active_streaming: FakeStreamingSession | None,
        live_state: dict[str, Any] | None,
    ) -> None:
        _ = message
        final_replies.append(BackendReply(text=text))
        if active_streaming is not None and active_streaming.has_started():
            await active_streaming.close(turn.presenter.build_final_card(live_state or {}, fallback_text=text))

    runtime = TurnRuntimeContext(
        config=SimpleNamespace(feishu=SimpleNamespace(stream_mode="card")),
        store=store,
        messenger=object(),
        typing_manager=FakeTypingManager(),
        session_ux=SimpleNamespace(
            format_cwd=lambda cwd, session=None, release_channel=None: str(cwd),
            label_session_if_needed=lambda current, summary: current,
            shorten=lambda text, max_length=96: str(text)[:max_length],
        ),
        streaming_session_factory=lambda current_messenger: streaming,
        execution_coordinator=SimpleNamespace(start_run=lambda *args, **kwargs: None, finish_run=lambda *args, **kwargs: None),
        build_card_action_context=lambda message, session_key: {},
        streaming_route_for_message=lambda message: SimpleNamespace(reply_to_message_id="", root_id="", force_new_message=False),
        root_id_for_message=lambda message: "",
        is_card_action_message=lambda message: False,
        build_session_key=lambda message: "session:test",
        remember_outbound_aliases=lambda message, session_key, alias_ids: None,
        reply_final=reply_final,
        live_turn_presenter=None,
        binding_store=binding_store,  # type: ignore[arg-type]
        runtime_service=runtime_service,
    )
    turn = BackendTurnSession(runtime, _build_message(), "session:relay_1", session)

    await turn.run("trace plan status", "trace official inProgress status")

    assert streaming.final_card is not None
    markdown_blocks = _extract_markdown_blocks(streaming.final_card)
    rendered_card_text = "\n\n".join(markdown_blocks)

    print("\n=== PLAN STATUS E2E LOGS ===")
    for record in caplog.records:
        if "plan" in record.name or "plan" in record.getMessage().lower():
            print(f"{record.levelname} {record.name}: {record.getMessage()}")

    print("\n=== FINAL FEISHU CARD MARKDOWN ===")
    print(rendered_card_text)

    assert any("raw_status=inProgress normalized_status=in_progress" in record.getMessage() for record in caplog.records)
    assert "Inspect runtime" in rendered_card_text
    assert "Wire mapper" in rendered_card_text
    assert "◉ Wire mapper" in rendered_card_text
    assert "inProgress" not in rendered_card_text
