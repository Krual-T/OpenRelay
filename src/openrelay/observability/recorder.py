from __future__ import annotations

from typing import Any

from openrelay.core import IncomingMessage, utc_now

from .context import bind_trace_id, build_message_context
from .models import MessageEventRecord, MessageTraceContext
from .store import MessageEventStore


class MessageTraceRecorder:
    def __init__(
        self,
        store: MessageEventStore,
        *,
        max_payload_bytes: int = 8192,
        max_summary_length: int = 240,
    ) -> None:
        self.store = store
        self.max_payload_bytes = max(max_payload_bytes, 256)
        self.max_summary_length = max(max_summary_length, 32)

    def bind_message(self, message: IncomingMessage) -> tuple[IncomingMessage, MessageTraceContext]:
        context = build_message_context(message)
        return bind_trace_id(message, context), context

    def enrich_context(self, context: MessageTraceContext, **changes: str) -> MessageTraceContext:
        return context.with_updates(**changes)

    def record(
        self,
        context: MessageTraceContext,
        *,
        stage: str,
        event_type: str,
        level: str = "info",
        summary: str = "",
        payload: dict[str, Any] | None = None,
        reply_message_id: str = "",
    ) -> int:
        effective_context = context if not reply_message_id else context.with_updates(reply_message_id=reply_message_id)
        record = MessageEventRecord(
            trace_id=effective_context.trace_id,
            occurred_at=utc_now(),
            level=level,
            stage=stage,
            event_type=event_type,
            backend=effective_context.backend,
            relay_session_id=effective_context.relay_session_id,
            session_key=effective_context.session_key,
            execution_key=effective_context.execution_key,
            turn_id=effective_context.turn_id,
            native_session_id=effective_context.native_session_id,
            incoming_event_id=effective_context.incoming_event_id,
            incoming_message_id=effective_context.incoming_message_id,
            reply_message_id=effective_context.reply_message_id,
            chat_id=effective_context.chat_id,
            root_id=effective_context.root_id,
            thread_id=effective_context.thread_id,
            parent_id=effective_context.parent_id,
            source_kind=effective_context.source_kind,
            summary=self._trim_summary(summary),
            payload=self._trim_payload(payload or {}),
        )
        return self.store.append(record)

    def _trim_summary(self, summary: str) -> str:
        normalized = str(summary or "").strip()
        if len(normalized) <= self.max_summary_length:
            return normalized
        return f"{normalized[: self.max_summary_length - 1]}…"

    def _trim_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = {str(key): value for key, value in payload.items()}
        encoded = self._encode_payload(normalized)
        if len(encoded) <= self.max_payload_bytes:
            return normalized
        truncated: dict[str, Any] = {}
        for key, value in normalized.items():
            if isinstance(value, str):
                truncated[key] = value[:1024]
            else:
                truncated[key] = value
            encoded = self._encode_payload({**truncated, "truncated": True, "original_size": len(encoded)})
            if len(encoded) > self.max_payload_bytes:
                break
        truncated["truncated"] = True
        truncated["original_size"] = len(encoded)
        return truncated

    def _encode_payload(self, payload: dict[str, Any]) -> bytes:
        import json

        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
