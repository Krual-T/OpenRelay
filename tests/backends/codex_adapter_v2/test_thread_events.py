from __future__ import annotations

from openrelay.backends.codex_adapter_v2.notifications import (
    ServerNotification,
    TurnCompletedNotification,
    TurnStartedNotification,
)
from openrelay.backends.codex_adapter_v2.requests import ServerRequest
from openrelay.backends.codex_adapter_v2.thread_events import (
    FeedbackThreadEvent,
    ThreadBufferedEvent,
    ThreadEventSnapshot,
    ThreadEventStore,
)

THREAD_ID = "00000000-0000-0000-0000-000000000011"


def _notification(variant: str, params: dict[str, object] | None = None) -> ServerNotification:
    return ServerNotification(variant=variant, method="method", params=params or {"threadId": THREAD_ID})


def _request() -> ServerRequest:
    return ServerRequest(
        variant="DynamicToolCall",
        method="item/tool/call",
        request_id=1,
        params={"threadId": THREAD_ID},
    )


def test_thread_event_store_initializes_official_state_fields() -> None:
    store = ThreadEventStore.new(capacity=3)

    assert store.session is None
    assert store.turns == []
    assert list(store.buffer) == []
    assert store.pending_interactive_replay.server_requests == []
    assert store.active_turn_id is None
    assert store.input_state is None
    assert store.capacity == 3
    assert store.active is False


def test_set_turns_tracks_last_in_progress_turn() -> None:
    store = ThreadEventStore.new(capacity=3)

    store.set_turns(
        [
            {"id": "turn_1", "status": "inProgress"},
            {"id": "turn_2", "status": "completed"},
            {"id": "turn_3", "status": "inProgress"},
        ]
    )

    assert store.active_turn_id == "turn_3"


def test_push_notification_updates_active_turn_and_buffers_event() -> None:
    store = ThreadEventStore.new(capacity=3)
    notification = ServerNotification(
        variant="TurnStarted",
        method="turn/started",
        params=TurnStartedNotification(
            thread_id=THREAD_ID,
            turn={"id": "turn_1", "status": "inProgress"},
        ),
    )

    store.push_notification(notification)

    assert store.active_turn_id == "turn_1"
    assert list(store.buffer) == [ThreadBufferedEvent.notification(notification)]


def test_turn_completed_only_clears_matching_active_turn() -> None:
    store = ThreadEventStore.new(capacity=4)
    store.active_turn_id = "turn_1"

    store.push_notification(
        ServerNotification(
            variant="TurnCompleted",
            method="turn/completed",
            params=TurnCompletedNotification(
                thread_id=THREAD_ID,
                turn={"id": "turn_2", "status": "completed"},
            ),
        )
    )

    assert store.active_turn_id == "turn_1"

    store.push_notification(
        ServerNotification(
            variant="TurnCompleted",
            method="turn/completed",
            params=TurnCompletedNotification(
                thread_id=THREAD_ID,
                turn={"id": "turn_1", "status": "completed"},
            ),
        )
    )

    assert store.active_turn_id is None


def test_thread_closed_clears_active_turn() -> None:
    store = ThreadEventStore.new(capacity=3)
    store.active_turn_id = "turn_1"

    store.push_notification(_notification("ThreadClosed"))

    assert store.active_turn_id is None


def test_push_request_records_pending_replay_and_evicts_oldest_event() -> None:
    store = ThreadEventStore.new(capacity=2)
    first = _notification("HookStarted")
    second = _request()
    third = _notification("HookCompleted")

    store.push_notification(first)
    store.push_request(second)
    store.push_notification(third)

    assert list(store.buffer) == [
        ThreadBufferedEvent.request(second),
        ThreadBufferedEvent.notification(third),
    ]
    assert store.pending_interactive_replay.server_requests == [second]


def test_snapshot_returns_current_session_turns_events_and_input_state() -> None:
    store = ThreadEventStore.new_with_session(
        capacity=3,
        session={"threadId": THREAD_ID},
        turns=[{"id": "turn_1", "status": "completed"}],
    )
    store.input_state = {"text": "继续"}
    request = _request()
    store.push_request(request)

    assert store.snapshot() == ThreadEventSnapshot(
        session={"threadId": THREAD_ID},
        turns=[{"id": "turn_1", "status": "completed"}],
        events=[ThreadBufferedEvent.request(request)],
        input_state={"text": "继续"},
    )


def test_rebase_buffer_after_session_refresh_keeps_only_official_survivors() -> None:
    store = ThreadEventStore.new(capacity=10)
    request = _request()
    feedback = FeedbackThreadEvent(
        category="bug",
        include_logs=True,
        feedback_audience="maintainer",
        result="sent",
    )
    events = [
        ThreadBufferedEvent.notification(_notification("TurnStarted")),
        ThreadBufferedEvent.notification(_notification("HookStarted")),
        ThreadBufferedEvent.request(request),
        ThreadBufferedEvent.feedback_submission(feedback),
        ThreadBufferedEvent.notification(_notification("HookCompleted")),
    ]
    store.buffer.extend(events)

    store.rebase_buffer_after_session_refresh()

    assert list(store.buffer) == events[1:]


def test_event_survives_session_refresh_matches_official_rules() -> None:
    assert ThreadEventStore.event_survives_session_refresh(ThreadBufferedEvent.request(_request())) is True
    assert ThreadEventStore.event_survives_session_refresh(
        ThreadBufferedEvent.notification(_notification("HookStarted"))
    ) is True
    assert ThreadEventStore.event_survives_session_refresh(
        ThreadBufferedEvent.notification(_notification("HookCompleted"))
    ) is True
    assert ThreadEventStore.event_survives_session_refresh(
        ThreadBufferedEvent.feedback_submission(
            FeedbackThreadEvent(
                category="bug",
                include_logs=False,
                feedback_audience="maintainer",
                result="sent",
            )
        )
    ) is True
    assert ThreadEventStore.event_survives_session_refresh(
        ThreadBufferedEvent.notification(_notification("TurnStarted"))
    ) is False
