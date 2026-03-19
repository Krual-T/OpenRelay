from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from openrelay.core import utc_now


@dataclass(slots=True, frozen=True)
class MessageEventRecord:
    trace_id: str
    occurred_at: str = field(default_factory=utc_now)
    level: str = "info"
    stage: str = ""
    event_type: str = ""
    backend: str = ""
    relay_session_id: str = ""
    session_key: str = ""
    execution_key: str = ""
    turn_id: str = ""
    native_session_id: str = ""
    incoming_event_id: str = ""
    incoming_message_id: str = ""
    reply_message_id: str = ""
    chat_id: str = ""
    root_id: str = ""
    thread_id: str = ""
    parent_id: str = ""
    source_kind: str = ""
    summary: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    row_id: int = 0


@dataclass(slots=True, frozen=True)
class MessageTraceContext:
    trace_id: str
    relay_session_id: str = ""
    session_key: str = ""
    execution_key: str = ""
    turn_id: str = ""
    native_session_id: str = ""
    backend: str = ""
    incoming_event_id: str = ""
    incoming_message_id: str = ""
    chat_id: str = ""
    root_id: str = ""
    thread_id: str = ""
    parent_id: str = ""
    source_kind: str = ""
    reply_message_id: str = ""

    def with_updates(self, **changes: str) -> "MessageTraceContext":
        normalized = {key: str(value or "").strip() for key, value in changes.items() if value is not None}
        return replace(self, **normalized)
