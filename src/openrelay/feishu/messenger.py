from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

import lark_oapi as lark
from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody, ReplyMessageRequest, ReplyMessageRequestBody, UpdateMessageRequest, UpdateMessageRequestBody
from lark_oapi.core.enum import AccessTokenType, HttpMethod, LogLevel
from lark_oapi.core.model import BaseRequest

from openrelay.core import AppConfig

from .common import LOGGER, _ensure_success, _guess_file_suffix, _json_dumps, _read_text, _response_bytes, _response_headers, _response_payload, summarize_text_entities
from .parsing import build_markdown_post_content, split_text
from .types import SentMessageRef


def sent_message_ref_from_payload(payload: dict[str, Any]) -> SentMessageRef:
    data = payload.get("data")
    if not isinstance(data, dict):
        data = {}
    ref = SentMessageRef(
        message_id=_read_text(data.get("message_id")),
        root_id=_read_text(data.get("root_id")),
        thread_id=_read_text(data.get("thread_id")),
        parent_id=_read_text(data.get("parent_id")),
        upper_message_id=_read_text(data.get("upper_message_id")),
    )
    LOGGER.info(
        "feishu outbound payload message_id=%s root_id=%s thread_id=%s parent_id=%s upper_message_id=%s",
        ref.message_id,
        ref.root_id,
        ref.thread_id,
        ref.parent_id,
        ref.upper_message_id,
    )
    return ref


class FeishuMessenger:
    def __init__(self, config: AppConfig):
        self.config = config
        self.client = lark.Client.builder().app_id(config.feishu.app_id).app_secret(config.feishu.app_secret).log_level(LogLevel.INFO).build()

    async def close(self) -> None:
        return None

    def ensure_success(self, response: object, label: str) -> None:
        _ensure_success(response, label)

    async def resolve_bot_open_id(self) -> str:
        if self.config.feishu.bot_open_id:
            return self.config.feishu.bot_open_id
        request = BaseRequest.builder().http_method(HttpMethod.GET).uri("/open-apis/bot/v3/info").token_types({AccessTokenType.TENANT}).build()
        response = await self.client.arequest(request)
        _ensure_success(response, "Feishu bot info")
        payload = _response_payload(response)
        bot_open_id = _read_text(payload.get("bot", {}).get("open_id") or payload.get("data", {}).get("bot", {}).get("open_id"))
        if not bot_open_id:
            raise RuntimeError(f"Feishu bot open_id missing: {payload}")
        self.config.feishu.bot_open_id = bot_open_id
        return bot_open_id

    async def reply_message(self, message_id: str, msg_type: str, content: str, *, reply_in_thread: bool = True) -> dict[str, Any]:
        if msg_type == "interactive":
            summary = summarize_text_entities(content)
            if (
                summary["nbsp_entity_count"]
                or summary["nbsp_char_count"]
                or summary["question_mark_count"]
            ):
                LOGGER.info(
                    "feishu reply interactive message_id=%s len=%s nbsp_entity=%s nbsp_char=%s question=%s preview=%r",
                    message_id,
                    summary["length"],
                    summary["nbsp_entity_count"],
                    summary["nbsp_char_count"],
                    summary["question_mark_count"],
                    summary["preview"],
                )
        request = ReplyMessageRequest.builder().message_id(message_id).request_body(
            ReplyMessageRequestBody.builder().msg_type(msg_type).content(content).reply_in_thread(reply_in_thread).uuid(uuid.uuid4().hex).build()
        ).build()
        response = await self.client.im.v1.message.areply(request)
        _ensure_success(response, f"Feishu reply {msg_type}")
        return _response_payload(response)

    async def create_message(self, chat_id: str, msg_type: str, content: str, *, root_id: str = "") -> dict[str, Any]:
        if msg_type == "interactive":
            summary = summarize_text_entities(content)
            if (
                summary["nbsp_entity_count"]
                or summary["nbsp_char_count"]
                or summary["question_mark_count"]
            ):
                LOGGER.info(
                    "feishu create interactive chat_id=%s len=%s nbsp_entity=%s nbsp_char=%s question=%s preview=%r",
                    chat_id,
                    summary["length"],
                    summary["nbsp_entity_count"],
                    summary["nbsp_char_count"],
                    summary["question_mark_count"],
                    summary["preview"],
                )
        body: dict[str, Any] = {
            "receive_id": chat_id,
            "msg_type": msg_type,
            "content": content,
            "uuid": uuid.uuid4().hex,
        }
        if root_id:
            body["root_id"] = root_id
        request = BaseRequest.builder().http_method(HttpMethod.POST).uri("/open-apis/im/v1/messages").token_types({AccessTokenType.TENANT, AccessTokenType.USER}).queries([("receive_id_type", "chat_id")]).headers({"Content-Type": "application/json; charset=utf-8"}).body(body).build()
        response = await self.client.arequest(request)
        _ensure_success(response, f"Feishu create {msg_type}")
        return _response_payload(response)

    async def update_message(self, message_id: str, msg_type: str, content: str) -> dict[str, Any]:
        if msg_type == "interactive":
            summary = summarize_text_entities(content)
            if (
                summary["nbsp_entity_count"]
                or summary["nbsp_char_count"]
                or summary["question_mark_count"]
            ):
                LOGGER.info(
                    "feishu update interactive message_id=%s len=%s nbsp_entity=%s nbsp_char=%s question=%s preview=%r",
                    message_id,
                    summary["length"],
                    summary["nbsp_entity_count"],
                    summary["nbsp_char_count"],
                    summary["question_mark_count"],
                    summary["preview"],
                )
        request = UpdateMessageRequest.builder().message_id(message_id).request_body(
            UpdateMessageRequestBody.builder().msg_type(msg_type).content(content).build()
        ).build()
        response = await self.client.im.v1.message.aupdate(request)
        _ensure_success(response, f"Feishu update {msg_type}")
        return _response_payload(response)

    async def patch_message(self, message_id: str, content: str) -> dict[str, Any]:
        summary = summarize_text_entities(content)
        if (
            summary["nbsp_entity_count"]
            or summary["nbsp_char_count"]
            or summary["question_mark_count"]
        ):
            LOGGER.info(
                "feishu patch interactive message_id=%s len=%s nbsp_entity=%s nbsp_char=%s question=%s preview=%r",
                message_id,
                summary["length"],
                summary["nbsp_entity_count"],
                summary["nbsp_char_count"],
                summary["question_mark_count"],
                summary["preview"],
            )
        request = PatchMessageRequest.builder().message_id(message_id).request_body(
            PatchMessageRequestBody.builder().content(content).build()
        ).build()
        response = await self.client.im.v1.message.apatch(request)
        _ensure_success(response, "Feishu patch message")
        return _response_payload(response)

    async def download_message_resource_to_file(self, message_id: str, file_key: str, *, resource_type: str = "image") -> str:
        request = BaseRequest.builder().http_method(HttpMethod.GET).uri(
            f"/open-apis/im/v1/messages/{message_id}/resources/{file_key}"
        ).token_types({AccessTokenType.TENANT}).queries([("type", resource_type)]).build()
        response = await self.client.arequest(request)
        _ensure_success(response, f"Feishu download {resource_type} resource")
        content = _response_bytes(response)
        if not content:
            raise RuntimeError(f"Feishu download {resource_type} resource failed: empty content")
        headers = _response_headers(response)
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        suffix = _guess_file_suffix(content_type)
        media_dir = (self.config.data_dir / "feishu-media").resolve()
        media_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="feishu-inbound-", suffix=suffix, dir=media_dir, delete=False) as handle:
            handle.write(content)
            return str(Path(handle.name).resolve())

    async def send_text(
        self,
        chat_id: str,
        text: str,
        *,
        reply_to_message_id: str = "",
        root_id: str = "",
        force_new_message: bool = False,
    ) -> tuple[SentMessageRef, ...]:
        sent_messages: list[SentMessageRef] = []
        for chunk in split_text(text):
            if reply_to_message_id and not force_new_message:
                try:
                    payload = await self.reply_message(
                        reply_to_message_id,
                        "post",
                        build_markdown_post_content(chunk),
                        reply_in_thread=True,
                    )
                    sent_messages.append(sent_message_ref_from_payload(payload))
                    continue
                except Exception:
                    LOGGER.exception("reply text failed for message_id=%s", reply_to_message_id)
            payload = await self.create_message(chat_id, "post", build_markdown_post_content(chunk), root_id=root_id)
            sent_messages.append(sent_message_ref_from_payload(payload))
        return tuple(sent_messages)

    async def send_interactive_card(
        self,
        chat_id: str,
        card: dict[str, Any],
        *,
        reply_to_message_id: str = "",
        root_id: str = "",
        force_new_message: bool = False,
        update_message_id: str = "",
    ) -> SentMessageRef:
        content = _json_dumps(card)
        summary = summarize_text_entities(content)
        if (
            summary["nbsp_entity_count"]
            or summary["nbsp_char_count"]
            or summary["question_mark_count"]
        ):
            LOGGER.info(
                "feishu send interactive card chat_id=%s update_message_id=%s reply_to=%s len=%s nbsp_entity=%s nbsp_char=%s question=%s preview=%r",
                chat_id,
                update_message_id,
                reply_to_message_id,
                summary["length"],
                summary["nbsp_entity_count"],
                summary["nbsp_char_count"],
                summary["question_mark_count"],
                summary["preview"],
            )
        if update_message_id:
            try:
                await self.patch_message(update_message_id, content)
                return SentMessageRef(message_id=update_message_id)
            except Exception:
                LOGGER.exception("patch interactive card failed for message_id=%s", update_message_id)
        if reply_to_message_id and not force_new_message:
            try:
                payload = await self.reply_message(reply_to_message_id, "interactive", content, reply_in_thread=True)
                return sent_message_ref_from_payload(payload)
            except Exception:
                LOGGER.exception(
                    "reply interactive card failed for message_id=%s after patch fallback message_id=%s",
                    reply_to_message_id,
                    update_message_id,
                )
        payload = await self.create_message(chat_id, "interactive", content, root_id=root_id)
        return sent_message_ref_from_payload(payload)
