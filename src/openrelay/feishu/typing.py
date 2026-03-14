from __future__ import annotations

from typing import Any

from lark_oapi.api.im.v1 import (
    CreateMessageReactionRequest,
    CreateMessageReactionRequestBody,
    DeleteMessageReactionRequest,
    Emoji,
)

from .messenger import FeishuMessenger
from .parsing import _read_text


TYPING_EMOJI = "Typing"


class FeishuTypingManager:
    def __init__(self, messenger: FeishuMessenger):
        self.messenger = messenger

    async def add(self, message_id: str) -> dict[str, Any]:
        request = CreateMessageReactionRequest.builder().message_id(message_id).request_body(
            CreateMessageReactionRequestBody.builder().reaction_type(Emoji.builder().emoji_type(TYPING_EMOJI).build()).build()
        ).build()
        response = await self.messenger.client.im.v1.message_reaction.acreate(request)
        self.messenger.ensure_success(response, "Feishu typing reaction create")
        return {"message_id": message_id, "reaction_id": _read_text(getattr(response.data, "reaction_id", ""))}

    async def remove(self, state: dict[str, Any] | None) -> None:
        if not state or not state.get("reaction_id"):
            return
        request = DeleteMessageReactionRequest.builder().message_id(state["message_id"]).reaction_id(state["reaction_id"]).build()
        response = await self.messenger.client.im.v1.message_reaction.adelete(request)
        self.messenger.ensure_success(response, "Feishu typing reaction delete")
