from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from openrelay.core import IncomingMessage, SessionRecord
from openrelay.feishu import FeishuMessenger

from .help import HelpRenderer
from .replying import RuntimeReplyPolicy


FallbackReply = Callable[[IncomingMessage, str, str], Awaitable[None]]


@dataclass(slots=True)
class RuntimeHelpService:
    messenger: FeishuMessenger
    renderer: HelpRenderer
    reply_policy: RuntimeReplyPolicy
    reply_fallback: FallbackReply

    async def send_help(self, message: IncomingMessage, session_key: str, session: SessionRecord, available_backends: list[str]) -> None:
        card = self.renderer.build_card(
            session,
            available_backends,
            self.reply_policy.build_card_action_context(message, session_key),
        )
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
            await self.reply_fallback(message, self.renderer.build_text(session, available_backends), "/help")
