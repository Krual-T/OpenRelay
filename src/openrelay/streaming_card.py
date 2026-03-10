from __future__ import annotations

import json
import time
from typing import Any

from lark_oapi.api.cardkit.v1 import (
    Card,
    ContentCardElementRequest,
    ContentCardElementRequestBody,
    CreateCardRequest,
    CreateCardRequestBody,
    UpdateCardElementRequest,
    UpdateCardElementRequestBody,
    UpdateCardRequest,
    UpdateCardRequestBody,
)

from openrelay.card_theme import build_status_heading, infer_final_tone
from openrelay.feishu import FeishuMessenger, _read_text
from openrelay.render import render_live_status_sections


BLANK_MARKDOWN = "\u200b"



def normalize_section_text(text: object) -> str:
    return str(text or "").strip()



def ensure_card_text(text: object) -> str:
    value = str(text or "")
    return value if value.strip() else BLANK_MARKDOWN



def normalize_sections(sections: dict[str, str] | None = None) -> dict[str, str]:
    sections = sections or {}
    return {
        "header": normalize_section_text(sections.get("header")),
        "details": normalize_section_text(sections.get("details")),
        "body": normalize_section_text(sections.get("body")),
    }



def sections_signature(sections: dict[str, str] | None = None) -> str:
    normalized = normalize_sections(sections)
    return json.dumps([normalized["header"], normalized["details"], normalized["body"]], ensure_ascii=False)



def create_markdown_element(element_id: str, content: str) -> dict[str, Any]:
    return {"tag": "markdown", "element_id": element_id, "content": ensure_card_text(content)}



def list_section_elements(sections: dict[str, str] | None = None) -> list[str]:
    normalized = normalize_sections(sections)
    return [element_id for element_id in ["header" if normalized["header"] else "", "details" if normalized["details"] else "", "body" if normalized["body"] else ""] if element_id]



def has_same_layout(left: dict[str, str] | None, right: dict[str, str] | None) -> bool:
    return list_section_elements(left) == list_section_elements(right)



def build_final_sections(text: str) -> dict[str, str]:
    content = normalize_section_text(text)
    tone = infer_final_tone(content)
    return {
        "header": build_status_heading(tone, "openrelay 回复"),
        "details": "",
        "body": content,
    }



def build_card_json(sections: dict[str, str], streaming_mode: bool = True, force_body: bool = False) -> dict[str, Any]:
    normalized = normalize_sections(sections)
    elements = []
    if normalized["header"]:
        elements.append(create_markdown_element("header", normalized["header"]))
    if normalized["details"]:
        elements.append(create_markdown_element("details", normalized["details"]))
    if normalized["body"] or force_body:
        elements.append(create_markdown_element("body", normalized["body"]))
    if not elements:
        elements.append(create_markdown_element("body", normalized["body"]))
    return {"schema": "2.0", "config": {"streaming_mode": streaming_mode}, "body": {"elements": elements}}


class FeishuStreamingSession:
    def __init__(self, messenger: FeishuMessenger, log: callable | None = None):
        self.messenger = messenger
        self.log = log
        self.state: dict[str, Any] | None = None
        self.queue = None
        self.closed = False
        self.pending_sections: dict[str, str] | None = None
        self.last_update_time = 0.0
        self.update_throttle_ms = 500
        import asyncio

        self.queue = asyncio.get_running_loop().create_future()
        self.queue.set_result(None)

    def next_sequence(self) -> int:
        if self.state is None:
            raise RuntimeError("Streaming session not started")
        self.state["sequence"] += 1
        return int(self.state["sequence"])

    async def start(self, receive_id: str, *, reply_to_message_id: str = "", root_id: str = "") -> None:
        if self.state is not None:
            return
        initial_sections = normalize_sections(render_live_status_sections({"heading": "正在启动 Codex", "status": "等待响应", "spinner_frame": 0}))
        create_response = await self.messenger.client.cardkit.v1.card.acreate(
            CreateCardRequest.builder().request_body(
                CreateCardRequestBody.builder().type("card_json").data(json.dumps(build_card_json(initial_sections, streaming_mode=True), ensure_ascii=False)).build()
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
                    "current_sections": initial_sections,
                    "current_signature": sections_signature(initial_sections),
                }
                return
            except Exception:
                pass
        payload = await self.messenger.create_message(receive_id, "interactive", card_content, root_id=root_id)
        self.state = {
            "card_id": card_id,
            "message_id": _read_text(payload.get("data", {}).get("message_id")),
            "sequence": 1,
            "current_sections": initial_sections,
            "current_signature": sections_signature(initial_sections),
        }
        if self.log is not None:
            self.log(f"streaming card started: {card_id}")

    async def update_card_content(self, element_id: str, text: str) -> None:
        if self.state is None:
            return
        sequence = self.next_sequence()
        response = await self.messenger.client.cardkit.v1.card_element.acontent(
            ContentCardElementRequest.builder().card_id(self.state["card_id"]).element_id(element_id).request_body(
                ContentCardElementRequestBody.builder().content(ensure_card_text(text)).sequence(sequence).uuid(f"c_{self.state['card_id']}_{element_id}_{sequence}").build()
            ).build()
        )
        self.messenger.ensure_success(response, "Feishu update card element content")

    async def update_card_element(self, element_id: str, text: str) -> None:
        if self.state is None:
            return
        sequence = self.next_sequence()
        response = await self.messenger.client.cardkit.v1.card_element.aupdate(
            UpdateCardElementRequest.builder().card_id(self.state["card_id"]).element_id(element_id).request_body(
                UpdateCardElementRequestBody.builder().element(json.dumps(create_markdown_element(element_id, text), ensure_ascii=False)).sequence(sequence).uuid(f"e_{self.state['card_id']}_{element_id}_{sequence}").build()
            ).build()
        )
        self.messenger.ensure_success(response, "Feishu update card element")

    async def update_card(self, sections: dict[str, str], *, streaming_mode: bool = True, force_body: bool = False) -> None:
        if self.state is None:
            return
        sequence = self.next_sequence()
        response = await self.messenger.client.cardkit.v1.card.aupdate(
            UpdateCardRequest.builder().card_id(self.state["card_id"]).request_body(
                UpdateCardRequestBody.builder().card(
                    Card.builder().type("card_json").data(json.dumps(build_card_json(sections, streaming_mode=streaming_mode, force_body=force_body), ensure_ascii=False)).build()
                ).sequence(sequence).uuid(f"u_{self.state['card_id']}_{sequence}").build()
            ).build()
        )
        self.messenger.ensure_success(response, "Feishu update card")

    async def apply_sections(self, sections: dict[str, str], animate_body: bool = True) -> None:
        if self.state is None:
            return
        next_sections = normalize_sections(sections)
        current_sections = normalize_sections(self.state.get("current_sections"))
        if not has_same_layout(current_sections, next_sections):
            await self.update_card(next_sections, streaming_mode=True)
            self.state["current_sections"] = next_sections
            self.state["current_signature"] = sections_signature(next_sections)
            return
        if next_sections["header"] != current_sections["header"]:
            await self.update_card_element("header", next_sections["header"])
        if next_sections["details"] != current_sections["details"]:
            await self.update_card_element("details", next_sections["details"])
        if next_sections["body"] != current_sections["body"]:
            if animate_body and next_sections["body"]:
                await self.update_card_content("body", next_sections["body"])
            else:
                await self.update_card_element("body", next_sections["body"])
        self.state["current_sections"] = next_sections
        self.state["current_signature"] = sections_signature(next_sections)

    async def update(self, live_state: dict[str, Any]) -> None:
        if self.state is None or self.closed:
            return
        next_sections = normalize_sections(render_live_status_sections(live_state))
        next_signature = sections_signature(next_sections)
        if next_signature == self.state.get("current_signature"):
            return
        now_ms = time.time() * 1000
        if now_ms - self.last_update_time < self.update_throttle_ms:
            self.pending_sections = next_sections
            return
        self.pending_sections = None
        self.last_update_time = now_ms
        await self.apply_sections(next_sections, animate_body=True)

    async def close(self, final_text: str | None) -> None:
        if self.state is None or self.closed:
            return
        self.closed = True
        if final_text is not None:
            next_sections = build_final_sections(final_text)
            await self.update_card(next_sections, streaming_mode=False, force_body=True)
            self.state["current_sections"] = next_sections
            self.state["current_signature"] = sections_signature(next_sections)
            return
        next_sections = normalize_sections(self.pending_sections or self.state.get("current_sections"))
        if sections_signature(next_sections) == self.state.get("current_signature"):
            return
        await self.apply_sections(next_sections, animate_body=False)

    def has_started(self) -> bool:
        return self.state is not None

    def is_active(self) -> bool:
        return self.state is not None and not self.closed
