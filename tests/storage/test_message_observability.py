from pathlib import Path

from openrelay.core import IncomingMessage
from openrelay.storage import StateStore
from tests.support.app import make_app_config, make_incoming_message, prepare_app_dirs


def test_message_event_store_supports_trace_session_and_message_queries(tmp_path: Path) -> None:
    config = make_app_config(tmp_path, max_session_messages=3)
    prepare_app_dirs(config, include_data_dir=False)
    store = StateStore(config)
    try:
        message, context = store.trace_recorder.bind_message(
            make_incoming_message("hello", event_suffix="1", sender_open_id="ou_1")
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
