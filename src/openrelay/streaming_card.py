from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable

from lark_oapi.api.cardkit.v1 import (
    Card,
    ContentCardElementRequest,
    ContentCardElementRequestBody,
    CreateCardRequest,
    CreateCardRequestBody,
    SettingsCardRequest,
    SettingsCardRequestBody,
    UpdateCardRequest,
    UpdateCardRequestBody,
)

from openrelay.feishu import FeishuMessenger, _read_text


STREAMING_ELEMENT_ID = "streaming_content"
BLANK_MARKDOWN = "\u200b"
DEFAULT_STREAM_UPDATE_THROTTLE_MS = 1000
DEFAULT_THINKING_TEXT = "思考中..."


def ensure_card_text(text: object) -> str:
    value = str(text or "")
    return value if value.strip() else BLANK_MARKDOWN


def build_streaming_card_json(content: str = DEFAULT_THINKING_TEXT) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "config": {
            "streaming_mode": True,
            "summary": {"content": DEFAULT_THINKING_TEXT},
        },
        "body": {
            "elements": [
                {
                    "tag": "markdown",
                    "element_id": STREAMING_ELEMENT_ID,
                    "content": ensure_card_text(content),
                }
            ]
        },
    }


def build_streaming_content(live_state: dict[str, Any] | None = None) -> str:
    live_state = live_state or {}
    partial_text = str(live_state.get("partial_text") or "").strip()
    if partial_text:
        return partial_text
    reasoning_text = str(live_state.get("reasoning_text") or live_state.get("last_reasoning") or "").strip()
    if reasoning_text:
        return f"💭 **Thinking...**\n\n{reasoning_text}"
    return DEFAULT_THINKING_TEXT


class FeishuStreamingSession:
    def __init__(self, messenger: FeishuMessenger, log: Callable[[str], None] | None = None):
        self.messenger = messenger
        self.log = log
        self.state: dict[str, Any] | None = None
        self.closed = False
        self.pending_content = ""
        self.last_update_time = 0.0
        self.update_throttle_ms = DEFAULT_STREAM_UPDATE_THROTTLE_MS
        self._lock = asyncio.Lock()

    def next_sequence(self) -> int:
        if self.state is None:
            raise RuntimeError("Streaming session not started")
        self.state["sequence"] += 1
        return int(self.state["sequence"])

    async def start(self, receive_id: str, *, reply_to_message_id: str = "", root_id: str = "") -> None:
        if self.state is not None:
            return
        initial_content = DEFAULT_THINKING_TEXT
        create_response = await self.messenger.client.cardkit.v1.card.acreate(
            CreateCardRequest.builder().request_body(
                CreateCardRequestBody.builder().type("card_json").data(json.dumps(build_streaming_card_json(initial_content), ensure_ascii=False)).build()
            ).build()
        )
        self.messenger.ensure_success(create_response, "Feishu create cardkit card")
        card_id = _read_text(getattr(create_response.data, "card_id", ""))
        if not card_id:
            raise RuntimeError("Create card failed: missing card_id")
        card_content = json.dumps({"type": "card", "data": {"card_id": card_id}}, ensure_ascii=False)
        if reply_to_message_id:
            try:
                payload = await self.messenger.reply_message(reply_to_message_id, "interactive", card_content, reply_in_thread=True)
                self.state = {
                    "card_id": card_id,
                    "message_id": _read_text(payload.get("data", {}).get("message_id")),
                    "sequence": 1,
                    "current_content": initial_content,
                }
                return
            except Exception:
                pass
        payload = await self.messenger.create_message(receive_id, "interactive", card_content, root_id=root_id)
        self.state = {
            "card_id": card_id,
            "message_id": _read_text(payload.get("data", {}).get("message_id")),
            "sequence": 1,
            "current_content": initial_content,
        }
        if self.log is not None:
            self.log(f"streaming card started: {card_id}")

    async def update_card_content(self, text: str) -> None:
        if self.state is None:
            return
        sequence = self.next_sequence()
        response = await self.messenger.client.cardkit.v1.card_element.acontent(
            ContentCardElementRequest.builder().card_id(self.state["card_id"]).element_id(STREAMING_ELEMENT_ID).request_body(
                ContentCardElementRequestBody.builder().content(ensure_card_text(text)).sequence(sequence).uuid(f"c_{self.state['card_id']}_{sequence}").build()
            ).build()
        )
        self.messenger.ensure_success(response, "Feishu update card element content")

    async def set_streaming_mode(self, enabled: bool) -> None:
        if self.state is None:
            return
        sequence = self.next_sequence()
        response = await self.messenger.client.cardkit.v1.card.asettings(
            SettingsCardRequest.builder().card_id(self.state["card_id"]).request_body(
                SettingsCardRequestBody.builder().settings(
                    json.dumps({"streaming_mode": enabled}, ensure_ascii=False)
                ).sequence(sequence).uuid(f"s_{self.state['card_id']}_{sequence}").build()
            ).build()
        )
        self.messenger.ensure_success(response, "Feishu update card settings")

    async def update_card_json(self, card_json: dict[str, Any]) -> None:
        if self.state is None:
            return
        sequence = self.next_sequence()
        response = await self.messenger.client.cardkit.v1.card.aupdate(
            UpdateCardRequest.builder().card_id(self.state["card_id"]).request_body(
                UpdateCardRequestBody.builder().card(
                    Card.builder().type("card_json").data(json.dumps(card_json, ensure_ascii=False)).build()
                ).sequence(sequence).uuid(f"j_{self.state['card_id']}_{sequence}").build()
            ).build()
        )
        self.messenger.ensure_success(response, "Feishu update card json")

    async def update(self, live_state: dict[str, Any]) -> None:
        if self.state is None or self.closed:
            return
        next_content = build_streaming_content(live_state)
        if next_content == str(self.state.get("current_content") or ""):
            return
        now_ms = time.time() * 1000
        if now_ms - self.last_update_time < self.update_throttle_ms:
            self.pending_content = next_content
            return
        self.pending_content = ""
        self.last_update_time = now_ms
        async with self._lock:
            if self.state is None or self.closed:
                return
            if next_content == str(self.state.get("current_content") or ""):
                return
            await self.update_card_content(next_content)
            self.state["current_content"] = next_content

    async def close(self, final_card: dict[str, Any] | None = None) -> None:
        if self.state is None or self.closed:
            return
        self.closed = True
        async with self._lock:
            if self.state is None:
                return
            if final_card is not None:
                await self.set_streaming_mode(False)
                await self.update_card_json(final_card)
                return
            next_content = self.pending_content.strip() or str(self.state.get("current_content") or "").strip()
            if next_content and next_content != str(self.state.get("current_content") or ""):
                await self.update_card_content(next_content)
                self.state["current_content"] = next_content
            await self.set_streaming_mode(False)

    def message_id(self) -> str:
        if self.state is None:
            return ""
        return str(self.state.get("message_id") or "")

    def has_started(self) -> bool:
        return self.state is not None

    def is_active(self) -> bool:
        return self.state is not None and not self.closed
