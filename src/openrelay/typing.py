from __future__ import annotations

from typing import Any

from openrelay.feishu import FEISHU_BASE_URL, _raise_api_error, _read_text, FeishuMessenger


TYPING_EMOJI = "Typing"


class FeishuTypingManager:
    def __init__(self, messenger: FeishuMessenger):
        self.messenger = messenger

    async def add(self, message_id: str) -> dict[str, Any]:
        token = await self.messenger.get_tenant_access_token()
        response = await self.messenger._client.post(
            f"{FEISHU_BASE_URL}/im/v1/messages/{message_id}/reactions",
            headers={"Authorization": f"Bearer {token}"},
            json={"reaction_type": {"emoji_type": TYPING_EMOJI}},
        )
        _raise_api_error(response)
        payload = response.json()
        return {"message_id": message_id, "reaction_id": _read_text(payload.get("data", {}).get("reaction_id"))}

    async def remove(self, state: dict[str, Any] | None) -> None:
        if not state or not state.get("reaction_id"):
            return
        token = await self.messenger.get_tenant_access_token()
        response = await self.messenger._client.delete(
            f"{FEISHU_BASE_URL}/im/v1/messages/{state['message_id']}/reactions/{state['reaction_id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        _raise_api_error(response)
