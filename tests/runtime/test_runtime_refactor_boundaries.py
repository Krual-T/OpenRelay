from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from openrelay.core import AppConfig, BackendConfig, FeishuConfig, IncomingMessage, SessionRecord
from openrelay.feishu.types import SentMessageRef
from openrelay.runtime.message_content import message_summary_text
from openrelay.runtime.message_application import RuntimeMessageApplicationService
from openrelay.runtime.orchestrator import RuntimeOrchestrator
from openrelay.runtime.reply_service import RuntimeReplyService
from openrelay.runtime.replying import ReplyRoute
from openrelay.runtime.turn import TurnRuntimeContext
from openrelay.runtime.turn_execution import DEFAULT_IMAGE_PROMPT, RuntimeTurnExecutionService
from openrelay.storage import StateStore


def make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        cwd=tmp_path,
        port=3100,
        webhook_path="/feishu/webhook",
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "workspace",
        main_workspace_dir=tmp_path / "main",
        develop_workspace_dir=tmp_path / "develop",
        max_request_bytes=1024,
        max_session_messages=20,
        feishu=FeishuConfig(app_id="app", app_secret="secret", verify_token="verify-token", bot_open_id="ou_bot"),
        backend=BackendConfig(codex_sessions_dir=tmp_path / "native"),
    )


def build_message(*, text: str = "hello", local_image_paths: tuple[str, ...] = ()) -> IncomingMessage:
    return IncomingMessage(
        event_id="evt_1",
        message_id="om_1",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id="ou_user",
        text=text,
        local_image_paths=local_image_paths,
        actionable=True,
    )


class _IdleExecutionCoordinator:
    def active_run(self, execution_key: str) -> None:
        return None

    def queued_follow_up_count(self, execution_key: str) -> int:
        return 0

    def is_locked(self, execution_key: str) -> bool:
        return False

    async def try_handle_live_input(self, execution_key: str, message: IncomingMessage) -> bool:
        return False

    def enqueue_pending_input(self, execution_key: str, message: IncomingMessage):
        return None

    def dequeue_pending_input(self, execution_key: str):
        return None

    @asynccontextmanager
    async def lock_for(self, execution_key: str):
        yield


@pytest.mark.asyncio
async def test_message_application_uses_reply_keyword_contract_for_unauthorized_sender(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    for path in [config.workspace_root, config.main_workspace_dir, config.develop_workspace_dir]:
        path.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    reply_calls: list[dict[str, object]] = []

    async def fake_reply(
        message: IncomingMessage,
        text: str,
        *,
        command_reply: bool = False,
        command_name: str = "",
        trace_context: object | None = None,
    ) -> None:
        reply_calls.append(
            {
                "message": message,
                "text": text,
                "command_reply": command_reply,
                "command_name": command_name,
                "trace_context": trace_context,
            }
        )

    service = RuntimeMessageApplicationService(
        config=config,
        store=store,
        execution_coordinator=_IdleExecutionCoordinator(),
        message_dispatch=SimpleNamespace(resolve_and_decide=lambda message: None),
        is_allowed_user=lambda sender_open_id: False,
        trace_recorder=store.trace_recorder,
        reply=fake_reply,
        handle_command=lambda message, session_key, session: fake_reply(message, ""),
        run_backend_turn=lambda *args, **kwargs: fake_reply(args[0], ""),
        log_dispatch_resolution=lambda *args: None,
    )

    try:
        await service.handle(build_message())
    finally:
        store.close()

    assert len(reply_calls) == 1
    assert reply_calls[0]["text"] == "你没有权限使用 openrelay。"
    assert reply_calls[0]["command_reply"] is True
    assert reply_calls[0]["command_name"] == ""
    assert reply_calls[0]["trace_context"] is not None


@pytest.mark.asyncio
async def test_reply_service_routes_command_fallback_through_command_route(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    for path in [config.workspace_root, config.main_workspace_dir, config.develop_workspace_dir]:
        path.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    sent: list[dict[str, object]] = []

    class _Messenger:
        async def send_text(self, chat_id: str, text: str, **kwargs) -> tuple[SentMessageRef, ...]:
            sent.append({"chat_id": chat_id, "text": text, **kwargs})
            return (SentMessageRef(message_id="om_reply", root_id="om_root"),)

    policy = SimpleNamespace(
        default_route=lambda message: ReplyRoute(reply_to_message_id="default_reply", root_id="default_root"),
        command_route=lambda message, command_name: ReplyRoute(reply_to_message_id="command_reply", root_id=command_name),
    )
    session_scope = SimpleNamespace(
        build_session_key=lambda message: "p2p:oc_1",
        remember_outbound_aliases=lambda message, session_key, alias_groups: None,
    )
    service = RuntimeReplyService(
        config=config,
        messenger=_Messenger(),
        session_scope=session_scope,
        reply_policy=policy,
        live_turn_presenter=SimpleNamespace(build_final_card=lambda snapshot, fallback_text="": {"text": fallback_text}),
        trace_recorder=store.trace_recorder,
    )

    try:
        await service.reply_command_fallback(build_message(), "done", "/help")
    finally:
        store.close()

    assert sent == [
        {
            "chat_id": "oc_1",
            "text": "done",
            "reply_to_message_id": "command_reply",
            "root_id": "/help",
            "force_new_message": False,
        }
    ]


@pytest.mark.asyncio
async def test_turn_execution_builds_image_only_turn_from_shared_message_content(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeController:
        def __init__(self, runtime: TurnRuntimeContext, message: IncomingMessage, execution_key: str, presenter: object) -> None:
            captured["controller_args"] = (runtime, message, execution_key, presenter)

        def initialize(self, session: SessionRecord, *, trace_context: object | None = None) -> None:
            captured["initialized"] = {"session": session, "trace_context": trace_context}

    class _FakeApplication:
        def __init__(self, runtime: TurnRuntimeContext, message: IncomingMessage, execution_key: str, controller: object, event_bridge: object) -> None:
            captured["application_args"] = (runtime, message, execution_key, controller, event_bridge)

        async def run(self, message_summary: str, backend_prompt: str) -> None:
            captured["run_args"] = (message_summary, backend_prompt)

    monkeypatch.setattr("openrelay.runtime.turn_execution.TurnRunController", _FakeController)
    monkeypatch.setattr("openrelay.runtime.turn_execution.TurnApplicationService", _FakeApplication)
    monkeypatch.setattr("openrelay.runtime.turn_execution.TurnRuntimeEventBridge", lambda runtime, controller, presenter: "bridge")

    async def fake_reply(*args, **kwargs) -> None:
        raise AssertionError("reply should not be called for supported backend")

    runtime_context = TurnRuntimeContext(
        config=SimpleNamespace(feishu=SimpleNamespace(stream_mode="off")),
        store=SimpleNamespace(save_session=lambda session: session, append_message=lambda session_id, role, content: None),
        messenger=object(),
        typing_manager=SimpleNamespace(),
        session_ux=SimpleNamespace(
            format_cwd=lambda cwd, session=None: str(cwd),
            label_session_if_needed=lambda session, summary: session,
            shorten=lambda text, max_length=96: str(text)[:max_length],
        ),
        streaming_session_factory=lambda messenger: SimpleNamespace(),
        execution_coordinator=SimpleNamespace(start_run=lambda *args, **kwargs: None, finish_run=lambda *args, **kwargs: None),
        build_card_action_context=lambda message, session_key: {},
        streaming_route_for_message=lambda message: ReplyRoute(reply_to_message_id="", root_id=""),
        root_id_for_message=lambda message: "",
        is_card_action_message=lambda message: False,
        build_session_key=lambda message: "session:test",
        remember_outbound_aliases=lambda message, session_key, alias_ids: None,
        reply_final=lambda message, text, streaming, live_state, trace_context=None: None,
        trace_recorder=None,
        live_turn_presenter=None,
        binding_store=None,
        runtime_service=SimpleNamespace(backends={"codex": object()}),
    )
    service = RuntimeTurnExecutionService(
        runtime_context=runtime_context,
        runtime_backends={"codex": object()},
        reply=fake_reply,
        runtime_service=runtime_context.runtime_service,
    )

    message = build_message(text="", local_image_paths=("a.png", "b.png"))
    session = SessionRecord(session_id="relay_1", base_key="p2p:oc_1", backend="codex", cwd="/tmp")
    trace_context = object()

    await service.run(message, "session:relay_1", session, trace_context=trace_context)

    assert captured["initialized"] == {"session": session, "trace_context": trace_context}
    assert captured["run_args"] == (message_summary_text(message), DEFAULT_IMAGE_PROMPT)


@pytest.mark.asyncio
async def test_orchestrator_dispatch_message_delegates_to_message_application() -> None:
    orchestrator = RuntimeOrchestrator.__new__(RuntimeOrchestrator)
    captured: list[IncomingMessage] = []

    async def fake_handle(message: IncomingMessage) -> None:
        captured.append(message)

    orchestrator.message_application = SimpleNamespace(handle=fake_handle)
    message = build_message()

    await orchestrator.dispatch_message(message)

    assert captured == [message]
