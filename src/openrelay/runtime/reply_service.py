from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from openrelay.core import AppConfig, IncomingMessage
from openrelay.feishu import FeishuMessenger, FeishuStreamingSession
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

    async def reply(
        self,
        message: IncomingMessage,
        text: str,
        *,
        command_reply: bool = False,
        command_name: str = "",
    ) -> None:
        route = self.reply_policy.command_route(message, command_name) if command_reply else self.reply_policy.default_route(message)
        await self.send_text(message, text, route)

    async def reply_command_fallback(self, message: IncomingMessage, text: str, command_name: str) -> None:
        await self.reply(message, text, command_reply=True, command_name=command_name)

    async def reply_final(
        self,
        message: IncomingMessage,
        text: str,
        streaming: FeishuStreamingSession | None,
        live_state: dict[str, Any] | None = None,
    ) -> None:
        snapshot = live_state or {}
        if self.config.feishu.stream_mode == "card" and streaming is not None and streaming.has_started():
            try:
                await streaming.close(self.live_turn_presenter.build_final_card(snapshot, fallback_text=text))
                return
            except Exception:
                LOGGER.exception("streaming final card update failed for event_id=%s", message.event_id)
                try:
                    await streaming.close()
                except Exception:
                    LOGGER.exception("streaming fallback close failed for event_id=%s", message.event_id)
        await self.send_text(message, text, self.reply_policy.default_route(message))

    async def send_text(self, message: IncomingMessage, text: str, route: ReplyRoute) -> None:
        sent_messages = await self.messenger.send_text(
            message.chat_id,
            text,
            reply_to_message_id=route.reply_to_message_id,
            root_id=route.root_id,
            force_new_message=route.force_new_message,
        )
        session_key = self.session_scope.build_session_key(message)
        self.session_scope.remember_outbound_aliases(message, session_key, [sent_message.alias_ids() for sent_message in sent_messages])
