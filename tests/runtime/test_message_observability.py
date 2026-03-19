from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from openrelay.core import IncomingMessage, SessionRecord
from openrelay.feishu.types import SentMessageRef
from openrelay.runtime.dispatch_models import DispatchDecision, ResolvedMessageContext
from openrelay.runtime.message_application import RuntimeMessageApplicationService
from openrelay.runtime.reply_service import RuntimeReplyService
from openrelay.runtime.replying import RuntimeReplyPolicy
from openrelay.storage import StateStore
from tests.support.app import make_app_config, make_incoming_message, prepare_app_dirs


def build_message() -> IncomingMessage:
    return make_incoming_message("hello", event_suffix="1")


class _FakeExecutionCoordinator:
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
async def test_message_application_records_ingress_and_session_events(tmp_path: Path) -> None:
    config = make_app_config(tmp_path)
    prepare_app_dirs(config, include_data_dir=False)
    store = StateStore(config)
    try:
        message = build_message()
        session = SessionRecord(session_id="relay_1", base_key="p2p:oc_1", backend="codex", cwd=str(tmp_path))
        decision = DispatchDecision(
            kind="turn",
            execution_key="session:relay_1",
            resolved=ResolvedMessageContext(
                message=message,
                session_key="p2p:oc_1",
                session=session,
                is_top_level_control_command=False,
                is_top_level_message=True,
                control_key="p2p:oc_1",
            ),
        )
        captured: dict[str, object] = {}

        async def fake_reply(*args, **kwargs) -> None:
            return None

        async def fake_run_backend_turn(message: IncomingMessage, execution_key: str, session: SessionRecord, **kwargs) -> None:
            captured["trace_context"] = kwargs["trace_context"]

        service = RuntimeMessageApplicationService(
            config=config,
            store=store,
            execution_coordinator=_FakeExecutionCoordinator(),
            message_dispatch=SimpleNamespace(resolve_and_decide=lambda current_message: decision),
            is_allowed_user=lambda sender_open_id: True,
            trace_recorder=store.trace_recorder,
            reply=fake_reply,
            handle_command=lambda message, session_key, session: fake_reply(),
            run_backend_turn=fake_run_backend_turn,
            log_dispatch_resolution=lambda *args: None,
        )

        await service.handle(message)

        events = store.trace_query.list_events(incoming_message_id="om_1")
        assert [event.event_type for event in events] == [
            "ingress.message.received",
            "session.key.resolved",
            "session.loaded",
            "dispatch.turn.accepted",
        ]
        assert getattr(captured["trace_context"], "relay_session_id") == "relay_1"
    finally:
        store.close()


class _FakeMessenger:
    async def send_text(self, chat_id: str, text: str, **kwargs) -> tuple[SentMessageRef, ...]:
        return (SentMessageRef(message_id="om_reply_1", root_id="om_root_1"),)


@pytest.mark.asyncio
async def test_reply_service_records_reply_sent_event(tmp_path: Path) -> None:
    config = make_app_config(tmp_path)
    prepare_app_dirs(config, include_data_dir=False)
    store = StateStore(config)
    try:
        session_scope = SimpleNamespace(
            build_session_key=lambda message: "p2p:oc_1",
            remember_outbound_aliases=lambda message, session_key, alias_groups: None,
            root_id_for_message=lambda message: "",
            is_card_action_message=lambda message: False,
        )
        reply_service = RuntimeReplyService(
            config=config,
            messenger=_FakeMessenger(),
            session_scope=session_scope,
            reply_policy=RuntimeReplyPolicy(config, session_scope),
            live_turn_presenter=SimpleNamespace(build_final_card=lambda snapshot, fallback_text="": {"text": fallback_text}),
            trace_recorder=store.trace_recorder,
        )
        message, trace_context = store.trace_recorder.bind_message(build_message())
        trace_context = store.trace_recorder.enrich_context(trace_context, relay_session_id="relay_1", session_key="p2p:oc_1")

        await reply_service.reply(message, "done", trace_context=trace_context)

        events = store.trace_query.list_events(trace_id=message.trace_id)
        assert events[-1].event_type == "reply.sent"
        assert events[-1].reply_message_id == "om_reply_1"
    finally:
        store.close()
