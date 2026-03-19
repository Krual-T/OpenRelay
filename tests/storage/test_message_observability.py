from pathlib import Path

from openrelay.core import AppConfig, BackendConfig, FeishuConfig, IncomingMessage
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
        max_session_messages=3,
        feishu=FeishuConfig(app_id="app", app_secret="secret", verify_token="verify-token", bot_open_id="ou_bot"),
        backend=BackendConfig(codex_sessions_dir=tmp_path / "native"),
    )


def test_message_event_store_supports_trace_session_and_message_queries(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    for path in [config.workspace_root, config.main_workspace_dir, config.develop_workspace_dir]:
        path.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    try:
        message, context = store.trace_recorder.bind_message(
            IncomingMessage(
                event_id="evt_1",
                message_id="om_1",
                chat_id="oc_1",
                chat_type="p2p",
                sender_open_id="ou_1",
                text="hello",
                actionable=True,
            )
        )
        context = store.trace_recorder.enrich_context(
            context,
            relay_session_id="relay_1",
            session_key="p2p:oc_1",
            execution_key="session:relay_1",
            turn_id="turn_1",
            backend="codex",
        )
        store.trace_recorder.record(context, stage="ingress", event_type="ingress.message.received", summary="hello")
        store.trace_recorder.record(
            store.trace_recorder.enrich_context(context, reply_message_id="om_reply_1"),
            stage="egress",
            event_type="reply.sent",
            summary="done",
        )

        by_trace = store.trace_query.list_events(trace_id=message.trace_id)
        by_session = store.trace_query.list_events(relay_session_id="relay_1")
        by_turn = store.trace_query.list_events(turn_id="turn_1")
        by_message = store.trace_query.list_events(incoming_message_id="om_1")

        assert [event.event_type for event in by_trace] == ["ingress.message.received", "reply.sent"]
        assert [event.event_type for event in by_session] == ["ingress.message.received", "reply.sent"]
        assert [event.event_type for event in by_turn] == ["ingress.message.received", "reply.sent"]
        assert [event.event_type for event in by_message] == ["ingress.message.received", "reply.sent"]
        assert by_message[-1].reply_message_id == "om_reply_1"
    finally:
        store.close()
