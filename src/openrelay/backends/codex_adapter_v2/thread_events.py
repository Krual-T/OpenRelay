from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from .notifications import ServerNotification, TurnCompletedNotification, TurnStartedNotification
from .requests import ServerRequest

JSONValue: TypeAlias = Any


@dataclass(frozen=True, slots=True)
class FeedbackThreadEvent:
    category: str
    include_logs: bool
    feedback_audience: str
    result: str | dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class ThreadBufferedEvent:
    kind: Literal["Notification", "Request", "HistoryEntryResponse", "FeedbackSubmission"]
    notification_value: ServerNotification | None = None
    request_value: ServerRequest | None = None
    history_entry_response_value: dict[str, JSONValue] | None = None
    feedback_submission_value: FeedbackThreadEvent | None = None

    @classmethod
    def notification(cls, notification: ServerNotification) -> ThreadBufferedEvent:
        return cls(kind="Notification", notification_value=notification)

    @classmethod
    def request(cls, request: ServerRequest) -> ThreadBufferedEvent:
        return cls(kind="Request", request_value=request)

    @classmethod
    def history_entry_response(cls, response: Mapping[str, JSONValue]) -> ThreadBufferedEvent:
        return cls(kind="HistoryEntryResponse", history_entry_response_value=dict(response))

    @classmethod
    def feedback_submission(cls, event: FeedbackThreadEvent) -> ThreadBufferedEvent:
        return cls(kind="FeedbackSubmission", feedback_submission_value=event)


@dataclass(frozen=True, slots=True)
class ThreadEventSnapshot:
    session: dict[str, JSONValue] | None
    turns: list[dict[str, JSONValue]]
    events: list[ThreadBufferedEvent]
    input_state: dict[str, JSONValue] | None


@dataclass(slots=True)
class PendingInteractiveReplayState:
    server_notifications: list[ServerNotification] = field(default_factory=list)
    server_requests: list[ServerRequest] = field(default_factory=list)
    evicted_server_requests: list[ServerRequest] = field(default_factory=list)

    def note_server_notification(self, notification: ServerNotification) -> None:
        self.server_notifications.append(notification)

    def note_server_request(self, request: ServerRequest) -> None:
        self.server_requests.append(request)

    def note_evicted_server_request(self, request: ServerRequest) -> None:
        self.evicted_server_requests.append(request)


@dataclass(slots=True)
class ThreadEventStore:
    session: dict[str, JSONValue] | None
    turns: list[dict[str, JSONValue]]
    buffer: deque[ThreadBufferedEvent]
    pending_interactive_replay: PendingInteractiveReplayState
    active_turn_id: str | None
    input_state: dict[str, JSONValue] | None
    capacity: int
    active: bool

    @classmethod
    def new(cls, capacity: int) -> ThreadEventStore:
        return cls(
            session=None,
            turns=[],
            buffer=deque(),
            pending_interactive_replay=PendingInteractiveReplayState(),
            active_turn_id=None,
            input_state=None,
            capacity=capacity,
            active=False,
        )

    @classmethod
    def new_with_session(
        cls,
        capacity: int,
        session: Mapping[str, JSONValue],
        turns: list[dict[str, JSONValue]],
    ) -> ThreadEventStore:
        store = cls.new(capacity)
        store.set_session(session, turns)
        return store

    @staticmethod
    def event_survives_session_refresh(event: ThreadBufferedEvent) -> bool:
        if event.kind == "Request":
            return True
        if event.kind == "FeedbackSubmission":
            return True
        if event.kind == "Notification" and event.notification_value is not None:
            return event.notification_value.variant in {"HookStarted", "HookCompleted"}
        return False

    def set_session(
        self,
        session: Mapping[str, JSONValue],
        turns: list[dict[str, JSONValue]],
    ) -> None:
        self.session = dict(session)
        self.set_turns(turns)

    def rebase_buffer_after_session_refresh(self) -> None:
        self.buffer = deque(
            event for event in self.buffer if self.event_survives_session_refresh(event)
        )

    def set_turns(self, turns: list[dict[str, JSONValue]]) -> None:
        self.turns = list(turns)
        self.active_turn_id = next(
            (
                turn_id
                for turn in reversed(self.turns)
                if _turn_status(turn) == "inProgress" and (turn_id := _turn_id(turn)) is not None
            ),
            None,
        )

    def push_notification(self, notification: ServerNotification) -> None:
        self.pending_interactive_replay.note_server_notification(notification)
        if notification.variant == "TurnStarted":
            self.active_turn_id = _turn_id_from_notification(notification)
        elif notification.variant == "TurnCompleted":
            turn_id = _turn_id_from_notification(notification)
            if self.active_turn_id == turn_id:
                self.active_turn_id = None
        elif notification.variant == "ThreadClosed":
            self.active_turn_id = None
        self._push_event(ThreadBufferedEvent.notification(notification))

    def push_request(self, request: ServerRequest) -> None:
        self.pending_interactive_replay.note_server_request(request)
        self._push_event(ThreadBufferedEvent.request(request))

    def snapshot(self) -> ThreadEventSnapshot:
        return ThreadEventSnapshot(
            session=dict(self.session) if self.session is not None else None,
            turns=list(self.turns),
            events=list(self.buffer),
            input_state=dict(self.input_state) if self.input_state is not None else None,
        )

    def _push_event(self, event: ThreadBufferedEvent) -> None:
        self.buffer.append(event)
        if len(self.buffer) > self.capacity:
            removed = self.buffer.popleft()
            if removed.kind == "Request" and removed.request_value is not None:
                self.pending_interactive_replay.note_evicted_server_request(removed.request_value)


def _turn_id_from_notification(notification: ServerNotification) -> str | None:
    if isinstance(notification.params, (TurnStartedNotification, TurnCompletedNotification)):
        return _turn_id(notification.params.turn)
    if isinstance(notification.params, dict):
        turn = notification.params.get("turn")
        if isinstance(turn, Mapping):
            return _turn_id(turn)
    return None


def _turn_id(turn: Mapping[str, JSONValue]) -> str | None:
    turn_id = turn.get("id")
    return turn_id if isinstance(turn_id, str) else None


def _turn_status(turn: Mapping[str, JSONValue]) -> str | None:
    status = turn.get("status")
    return status if isinstance(status, str) else None
