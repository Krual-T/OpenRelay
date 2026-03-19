from __future__ import annotations

from dataclasses import dataclass

from .models import MessageEventRecord
from .store import MessageEventStore


@dataclass(slots=True)
class TraceQueryService:
    store: MessageEventStore

    def list_events(
        self,
        *,
        trace_id: str = "",
        relay_session_id: str = "",
        turn_id: str = "",
        incoming_message_id: str = "",
        limit: int = 200,
    ) -> list[MessageEventRecord]:
        if trace_id:
            return self.store.list_by_trace(trace_id, limit=limit)
        if relay_session_id:
            return self.store.list_by_session(relay_session_id, limit=limit)
        if turn_id:
            return self.store.list_by_turn(turn_id, limit=limit)
        if incoming_message_id:
            return self.store.list_by_message(incoming_message_id, limit=limit)
        return []
