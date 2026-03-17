from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from openrelay.core import IncomingMessage
from openrelay.feishu import FeishuMessenger

from .replying import RuntimeReplyPolicy


FallbackReply = Callable[[IncomingMessage, str, str], Awaitable[None]]


@dataclass(slots=True)
class CommandCardSender:
    messenger: FeishuMessenger
    reply_policy: RuntimeReplyPolicy
    reply_fallback: FallbackReply

    async def send(
        self,
        message: IncomingMessage,
        card: dict[str, object],
        *,
        fallback_text: str,
        command_name: str,
    ) -> None:
        try:
            await self.messenger.send_interactive_card(
                message.chat_id,
                card,
                reply_to_message_id=self.reply_policy.command_reply_target(message),
                root_id=self.reply_policy.root_id_for_message(message),
                force_new_message=self.reply_policy.should_force_new_message_for_command_card(message),
                update_message_id=self.reply_policy.command_card_update_target(message),
            )
        except Exception:
            await self.reply_fallback(message, fallback_text, command_name)
