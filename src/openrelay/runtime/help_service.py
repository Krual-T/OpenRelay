from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from openrelay.core import IncomingMessage, SessionRecord
from openrelay.feishu import FeishuMessenger

from .card_sender import CommandCardSender
from .help import HelpRenderer
from .replying import RuntimeReplyPolicy


FallbackReply = Callable[[IncomingMessage, str, str], Awaitable[None]]


@dataclass(slots=True)
class RuntimeHelpService:
    messenger: FeishuMessenger
    renderer: HelpRenderer
    reply_policy: RuntimeReplyPolicy
    reply_fallback: FallbackReply

    def _card_sender(self) -> CommandCardSender:
        return CommandCardSender(self.messenger, self.reply_policy, self.reply_fallback)

    async def send_help(self, message: IncomingMessage, session_key: str, session: SessionRecord, available_backends: list[str]) -> None:
        card = self.renderer.build_card(
            session,
            available_backends,
            self.reply_policy.build_card_action_context(message, session_key),
        )
        await self._card_sender().send(
            message,
            card,
            fallback_text=self.renderer.build_text(session, available_backends),
            command_name="/help",
        )
