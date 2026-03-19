from __future__ import annotations

from dataclasses import replace
import uuid

from openrelay.core import IncomingMessage

from .models import MessageTraceContext


def new_trace_id() -> str:
    return f"trace_{uuid.uuid4().hex[:16]}"


def build_message_context(message: IncomingMessage) -> MessageTraceContext:
    return MessageTraceContext(
        trace_id=str(message.trace_id or "").strip() or new_trace_id(),
        incoming_event_id=str(message.event_id or "").strip(),
        incoming_message_id=str(message.message_id or "").strip(),
        chat_id=str(message.chat_id or "").strip(),
        root_id=str(message.root_id or "").strip(),
        thread_id=str(message.thread_id or "").strip(),
        parent_id=str(message.parent_id or "").strip(),
        source_kind=str(message.source_kind or "").strip(),
    )


def bind_trace_id(message: IncomingMessage, context: MessageTraceContext) -> IncomingMessage:
    if message.trace_id == context.trace_id:
        return message
    return replace(message, trace_id=context.trace_id)
