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

from .messenger import FeishuMessenger, sent_message_ref_from_payload
from .parsing import _read_text
from .reply_card import (
    DEFAULT_THINKING_TEXT,
    STREAMING_ELEMENT_ID,
    build_complete_card,
    build_process_panel_text,
    build_streaming_card_json,
    build_streaming_card_signature,
    build_streaming_content,
    build_thinking_card_json,
)

DEFAULT_STREAM_UPDATE_THROTTLE_MS = 100
DEFAULT_CARD_STREAMING_WINDOW_SECONDS = 540.0
STREAMING_TIMEOUT_NOTICE = "流式显示已自动暂停，任务仍在继续。完成后会在此卡片更新最终结果。"


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
        self._pending_flush_task: asyncio.Task[None] | None = None
        self.streaming_mode_enabled = True
        self.started_at_ms = 0.0
        config = getattr(messenger, "config", None)
        feishu_config = getattr(config, "feishu", None)
        self.card_streaming_window_seconds = float(
            getattr(feishu_config, "card_streaming_window_seconds", DEFAULT_CARD_STREAMING_WINDOW_SECONDS)
            or DEFAULT_CARD_STREAMING_WINDOW_SECONDS
        )

    def next_sequence(self) -> int:
        if self.state is None:
            raise RuntimeError("Streaming session not started")
        self.state["sequence"] += 1
        return int(self.state["sequence"])

    async def start(self, receive_id: str, *, reply_to_message_id: str = "", root_id: str = "") -> None:
        if self.state is not None:
            return
        create_response = await self.messenger.client.cardkit.v1.card.acreate(
            CreateCardRequest.builder().request_body(
                CreateCardRequestBody.builder().type("card_json").data(json.dumps(build_thinking_card_json(), ensure_ascii=False)).build()
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
                sent_message = sent_message_ref_from_payload(payload)
                self.state = {
                    "card_id": card_id,
                    "message_id": sent_message.message_id,
                    "alias_ids": sent_message.alias_ids(),
                    "sequence": 1,
                    "current_content": "",
                    "card_signature": ("plain", ""),
                }
                self.started_at_ms = time.time() * 1000
                self.streaming_mode_enabled = True
                return
            except Exception:
                pass
        payload = await self.messenger.create_message(receive_id, "interactive", card_content, root_id=root_id)
        sent_message = sent_message_ref_from_payload(payload)
        self.state = {
            "card_id": card_id,
            "message_id": sent_message.message_id,
            "alias_ids": sent_message.alias_ids(),
            "sequence": 1,
            "current_content": "",
            "card_signature": ("plain", ""),
        }
        self.started_at_ms = time.time() * 1000
        self.streaming_mode_enabled = True
        if self.log is not None:
            self.log(f"streaming card started: {card_id}")

    def _streaming_window_elapsed(self, now_ms: float | None = None) -> bool:
        if self.started_at_ms <= 0:
            return False
        if self.card_streaming_window_seconds <= 0:
            return False
        current_ms = now_ms if now_ms is not None else time.time() * 1000
        return current_ms - self.started_at_ms >= self.card_streaming_window_seconds * 1000

    async def _disable_streaming_mode(self) -> None:
        if self.state is None or not self.streaming_mode_enabled:
            return
        await self.set_streaming_mode(False)
        self.streaming_mode_enabled = False

    async def freeze(self, live_state: dict[str, Any], *, notice_text: str = STREAMING_TIMEOUT_NOTICE) -> None:
        if self.state is None or self.closed or not self.streaming_mode_enabled:
            return
        self._cancel_pending_flush_task()
        async with self._lock:
            if self.state is None or self.closed or not self.streaming_mode_enabled:
                return
            await self.flush_pending_content()
            await self._disable_streaming_mode()
            waiting_card = build_complete_card(
                notice_text,
                panel_text=build_process_panel_text(live_state),
                panel_title="运行中状态",
            )
            await self.update_card_json(waiting_card)
            self.state["card_signature"] = ("frozen", "")
            self.state["current_content"] = ""

    async def update_card_content(self, text: str) -> None:
        if self.state is None:
            return
        sequence = self.next_sequence()
        response = await self.messenger.client.cardkit.v1.card_element.acontent(
            ContentCardElementRequest.builder().card_id(self.state["card_id"]).element_id(STREAMING_ELEMENT_ID).request_body(
                ContentCardElementRequestBody.builder().content(text).sequence(sequence).uuid(f"c_{self.state['card_id']}_{sequence}").build()
            ).build()
        )
        self.messenger.ensure_success(response, "Feishu update card element content")
        self.last_update_time = time.time() * 1000

    async def flush_pending_content(self) -> None:
        if self.state is None:
            return
        next_content = self.pending_content
        if not next_content or next_content == str(self.state.get("current_content") or ""):
            return
        self.pending_content = ""
        await self.update_card_content(next_content)
        self.state["current_content"] = next_content

    def _cancel_pending_flush_task(self) -> None:
        if self._pending_flush_task is None:
            return
        self._pending_flush_task.cancel()
        self._pending_flush_task = None

    def _schedule_pending_flush(self, delay_seconds: float) -> None:
        self._cancel_pending_flush_task()

        async def run() -> None:
            try:
                await asyncio.sleep(delay_seconds)
                async with self._lock:
                    if self.state is None or self.closed:
                        return
                    await self.flush_pending_content()
            except asyncio.CancelledError:
                return

        self._pending_flush_task = asyncio.create_task(run())

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
        if self.streaming_mode_enabled and self._streaming_window_elapsed():
            await self.freeze(live_state)
            return
        if not self.streaming_mode_enabled:
            return
        next_content = build_streaming_content(live_state)
        next_signature = build_streaming_card_signature(live_state)
        current_signature = self.state.get("card_signature") or ("plain", "")
        if next_content == str(self.state.get("current_content") or "") and next_signature == current_signature:
            return
        if next_signature != current_signature:
            self.pending_content = ""
            self._cancel_pending_flush_task()
            async with self._lock:
                if self.state is None or self.closed:
                    return
                current_signature = self.state.get("card_signature") or ("plain", "")
                if next_signature != current_signature:
                    await self.update_card_json(build_streaming_card_json(live_state))
                    self.state["card_signature"] = next_signature
                    self.state["current_content"] = next_content
                    self.last_update_time = time.time() * 1000
                    return
        if next_content == str(self.state.get("current_content") or ""):
            return
        now_ms = time.time() * 1000
        if now_ms - self.last_update_time < self.update_throttle_ms:
            self.pending_content = next_content
            remaining_ms = max(0.0, self.update_throttle_ms - (now_ms - self.last_update_time))
            self._schedule_pending_flush(remaining_ms / 1000)
            return
        self.pending_content = ""
        self._cancel_pending_flush_task()
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
        self._cancel_pending_flush_task()
        async with self._lock:
            if self.state is None:
                return
            await self.flush_pending_content()
            if final_card is not None:
                await self._disable_streaming_mode()
                await self.update_card_json(final_card)
                return
            await self._disable_streaming_mode()

    def message_id(self) -> str:
        if self.state is None:
            return ""
        return str(self.state.get("message_id") or "")

    def message_alias_ids(self) -> tuple[str, ...]:
        if self.state is None:
            return ()
        alias_ids = self.state.get("alias_ids")
        if isinstance(alias_ids, tuple):
            return alias_ids
        if isinstance(alias_ids, list):
            return tuple(str(item) for item in alias_ids if str(item))
        return ()

    def has_started(self) -> bool:
        return self.state is not None

    def is_active(self) -> bool:
        return self.state is not None and not self.closed and self.streaming_mode_enabled
