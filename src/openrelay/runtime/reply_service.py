from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from openrelay.core import AppConfig, IncomingMessage
from openrelay.feishu import FeishuMessenger, FeishuStreamingSession
from openrelay.observability import MessageTraceContext, MessageTraceRecorder
from openrelay.presentation.live_turn import LiveTurnPresenter
from openrelay.session import SessionScopeResolver

from .replying import ReplyRoute, RuntimeReplyPolicy


LOGGER = logging.getLogger("openrelay.runtime")


@dataclass(slots=True)
class RuntimeReplyService:
    config: AppConfig
    messenger: FeishuMessenger
    session_scope: SessionScopeResolver
    reply_policy: RuntimeReplyPolicy
    live_turn_presenter: LiveTurnPresenter
    trace_recorder: MessageTraceRecorder | None = None

    async def reply(
        self,
        message: IncomingMessage,
        text: str,
        *,
        command_reply: bool = False,
        command_name: str = "",
        trace_context: MessageTraceContext | None = None,
    ) -> None:
        route = self.reply_policy.command_route(message, command_name) if command_reply else self.reply_policy.default_route(message)
        await self.send_text(message, text, route, trace_context=trace_context)

    async def reply_command_fallback(
        self,
        message: IncomingMessage,
        text: str,
        command_name: str,
        trace_context: MessageTraceContext | None = None,
    ) -> None:
        await self.reply(message, text, command_reply=True, command_name=command_name, trace_context=trace_context)

    async def reply_final(
        self,
        message: IncomingMessage,
        text: str,
        streaming: FeishuStreamingSession | None,
        live_state: dict[str, Any] | None = None,
        trace_context: MessageTraceContext | None = None,
    ) -> None:
        snapshot = live_state or {}
        if self.config.feishu.stream_mode == "card" and streaming is not None and streaming.has_started():
            try:
                await streaming.close(self.live_turn_presenter.build_final_card(snapshot, fallback_text=text))
                if self.trace_recorder is not None:
                    _, base_context = self.trace_recorder.bind_message(message)
                    context = trace_context or base_context
                    reply_message_id = streaming.message_id()
                    self.trace_recorder.record(
                        self.trace_recorder.enrich_context(context, reply_message_id=reply_message_id),
                        stage="egress",
                        event_type="reply.sent",
                        summary=(text or "").strip()[:120],
                        payload={
                            "streaming": True,
                            "reply_message_ids": [reply_message_id] if reply_message_id else [],
                        },
                    )
                return
            except Exception:
                LOGGER.exception("streaming final card update failed for event_id=%s", message.event_id)
                try:
                    await streaming.close()
                except Exception:
                    LOGGER.exception("streaming fallback close failed for event_id=%s", message.event_id)
        await self.send_text(message, text, self.reply_policy.default_route(message), trace_context=trace_context)

    async def send_text(
        self,
        message: IncomingMessage,
        text: str,
        route: ReplyRoute,
        *,
        trace_context: MessageTraceContext | None = None,
    ) -> None:
        try:
            sent_messages = await self.messenger.send_text(
                message.chat_id,
                text,
                reply_to_message_id=route.reply_to_message_id,
                root_id=route.root_id,
                force_new_message=route.force_new_message,
            )
        except Exception as exc:
            self._record_reply_failure(message, route, text, exc, trace_context=trace_context)
            raise
        session_key = self.session_scope.build_session_key(message)
        self.session_scope.remember_outbound_aliases(message, session_key, [sent_message.alias_ids() for sent_message in sent_messages])
        self._record_reply_sent(message, route, text, sent_messages, trace_context=trace_context)

    def _record_reply_sent(
        self,
        message: IncomingMessage,
        route: ReplyRoute,
        text: str,
        sent_messages: tuple[Any, ...],
        *,
        trace_context: MessageTraceContext | None,
    ) -> None:
        if self.trace_recorder is None:
            return
        _, base_context = self.trace_recorder.bind_message(message)
        context = trace_context or base_context
        reply_ids = [sent_message.message_id for sent_message in sent_messages if getattr(sent_message, "message_id", "")]
        final_reply_id = reply_ids[-1] if reply_ids else ""
        self.trace_recorder.record(
            self.trace_recorder.enrich_context(context, reply_message_id=final_reply_id),
            stage="egress",
            event_type="reply.sent",
            summary=(text or "").strip()[:120],
            payload={
                "reply_to_message_id": route.reply_to_message_id,
                "root_id": route.root_id,
                "force_new_message": route.force_new_message,
                "reply_message_ids": reply_ids,
            },
        )

    def _record_reply_failure(
        self,
        message: IncomingMessage,
        route: ReplyRoute,
        text: str,
        exc: Exception,
        *,
        trace_context: MessageTraceContext | None,
    ) -> None:
        if self.trace_recorder is None:
            return
        _, base_context = self.trace_recorder.bind_message(message)
        context = trace_context or base_context
        self.trace_recorder.record(
            context,
            stage="egress",
            event_type="reply.failed",
            level="error",
            summary=str(exc),
            payload={
                "reply_to_message_id": route.reply_to_message_id,
                "root_id": route.root_id,
                "force_new_message": route.force_new_message,
                "text_preview": (text or "")[:120],
            },
        )
