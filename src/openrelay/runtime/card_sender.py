from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Awaitable, Callable

from openrelay.core import IncomingMessage
from openrelay.feishu import FeishuMessenger

from .replying import RuntimeReplyPolicy


FallbackReply = Callable[[IncomingMessage, str, str], Awaitable[None]]
LOGGER = logging.getLogger("openrelay.runtime.card_sender")


def _card_summary(card: dict[str, object]) -> dict[str, object]:
    header = card.get("header") if isinstance(card.get("header"), dict) else {}
    body = card.get("body") if isinstance(card.get("body"), dict) else {}
    elements = card.get("elements") if isinstance(card.get("elements"), list) else body.get("elements")
    tags: list[str] = []
    if isinstance(elements, list):
        for element in elements[:12]:
            if isinstance(element, dict):
                tags.append(str(element.get("tag") or "?"))
    title = ""
    if isinstance(header.get("title"), dict):
        title = str(header["title"].get("content") or "")
    return {
        "schema": str(card.get("schema") or ""),
        "title": title,
        "element_tags": tags,
        "element_count": len(elements) if isinstance(elements, list) else 0,
    }


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
            LOGGER.exception(
                "command card send failed command=%s event_id=%s message_id=%s reply_to=%s root_id=%s source_kind=%s card=%s",
                command_name,
                message.event_id,
                message.message_id,
                self.reply_policy.command_reply_target(message),
                self.reply_policy.root_id_for_message(message),
                message.source_kind,
                _card_summary(card),
            )
            await self.reply_fallback(message, fallback_text, command_name)
