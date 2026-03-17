from __future__ import annotations

import re
from typing import Any

from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1
from lark_oapi.core.model import RawRequest
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTrigger

from openrelay.core import AppConfig, IncomingMessage

from .common import (
    IMAGE_MESSAGE_PLACEHOLDER,
    LOGGER,
    MAX_TEXT_CHUNK,
    _coerce_card_action_event,
    _coerce_message_event,
    _event_header_attr,
    _extract_post_message_content,
    _json_dumps,
    _normalize_spaces,
    _read_attr_text,
    _read_nested_attr_text,
    _read_text,
    _safe_json_loads,
)
from .types import ParsedWebhook


def strip_mentions(text: str, mentions: list[object] | None = None) -> str:
    output = str(text or "")
    for mention in mentions or []:
        key = _read_attr_text(mention, "key")
        name = _read_attr_text(mention, "name")
        if key:
            output = output.replace(key, " ")
        if name:
            output = output.replace(f"@{name}", " ")
    output = re.sub(r"<at\b[^>]*>.*?</at>", " ", output, flags=re.IGNORECASE | re.DOTALL)
    return _normalize_spaces(output)


def is_bot_mentioned(bot_open_id: str, mentions: list[object] | None = None) -> bool:
    if not bot_open_id:
        return False
    for mention in mentions or []:
        mention_open_id = _read_nested_attr_text(mention, "id", "open_id")
        if mention_open_id == bot_open_id:
            return True
    return False


def parse_card_action_event(event: dict[str, Any] | P2CardActionTrigger) -> ParsedWebhook:
    sdk_event = _coerce_card_action_event(event)
    event_data = sdk_event.event
    if event_data is None:
        return ParsedWebhook(type="ignore")
    action_value = event_data.action.value if event_data.action is not None and isinstance(event_data.action.value, dict) else {}
    text = ""
    if isinstance(action_value, str):
        text = action_value.strip()
    elif isinstance(action_value, dict):
        text = _read_text(action_value.get("command") or action_value.get("text"))
    context = event_data.context
    operator = event_data.operator
    chat_id = _read_attr_text(context, "open_chat_id") or _read_attr_text(operator, "open_id")
    if not text or not chat_id:
        return ParsedWebhook(type="ignore")
    token = _read_attr_text(event_data, "token") or f"card-{__import__('uuid').uuid4().hex[:12]}"
    source_message_id = _read_attr_text(context, "open_message_id")
    return ParsedWebhook(
        type="message",
        message=IncomingMessage(
            event_id=_event_header_attr(sdk_event, "event_id") or f"card-action-{token}",
            message_id=source_message_id or f"card-action-{token}",
            reply_to_message_id=source_message_id,
            chat_id=chat_id,
            chat_type="group" if _read_attr_text(context, "open_chat_id") else "p2p",
            sender_open_id=_read_attr_text(operator, "open_id"),
            source_kind="card_action",
            root_id=_read_text(action_value.get("root_id") or action_value.get("rootId")),
            thread_id=_read_text(action_value.get("thread_id") or action_value.get("threadId") or action_value.get("root_id") or action_value.get("rootId")),
            parent_id="",
            session_key=_read_text(action_value.get("session_key") or action_value.get("sessionKey")),
            session_owner_open_id=_read_text(action_value.get("session_owner_open_id") or action_value.get("sessionOwnerOpenId")),
            text=text,
            actionable=True,
        ),
    )


def parse_message_event(config: AppConfig, event: dict[str, Any] | P2ImMessageReceiveV1) -> ParsedWebhook:
    sdk_event = _coerce_message_event(event)
    event_data = sdk_event.event
    message = event_data.message if event_data is not None else None
    if message is None:
        return ParsedWebhook(type="ignore")
    if not _read_attr_text(message, "message_id") or not _read_attr_text(message, "chat_id"):
        return ParsedWebhook(type="ignore")
    message_type = _read_attr_text(message, "message_type")
    if message_type not in {"text", "image", "post"}:
        return ParsedWebhook(type="ignore")
    mentions = list(getattr(message, "mentions", None) or [])
    content = _safe_json_loads(_read_attr_text(message, "content"))
    remote_image_keys: tuple[str, ...] = ()
    if message_type == "text":
        text = strip_mentions(_read_text(content.get("text")), mentions)
    elif message_type == "image":
        text = IMAGE_MESSAGE_PLACEHOLDER
        image_key = _read_text(content.get("image_key"))
        if not image_key:
            return ParsedWebhook(type="ignore")
        remote_image_keys = (image_key,)
    else:
        post_text, post_image_keys = _extract_post_message_content(content)
        text = strip_mentions(post_text, mentions)
        remote_image_keys = post_image_keys
        if not text and remote_image_keys:
            text = IMAGE_MESSAGE_PLACEHOLDER
        if not text and not remote_image_keys:
            return ParsedWebhook(type="ignore")
    sender = event_data.sender if event_data is not None else None
    sender_open_id = _read_nested_attr_text(sender, "sender_id", "open_id")
    chat_type = _read_attr_text(message, "chat_type") or "unknown"
    actionable = chat_type == "p2p" or config.feishu.group_reply_all or is_bot_mentioned(config.feishu.bot_open_id, mentions)
    incoming_message = IncomingMessage(
        event_id=_event_header_attr(sdk_event, "event_id") or _read_attr_text(message, "message_id"),
        message_id=_read_attr_text(message, "message_id"),
        chat_id=_read_attr_text(message, "chat_id"),
        chat_type=chat_type,
        sender_open_id=sender_open_id,
        source_kind="message",
        root_id=_read_attr_text(message, "root_id"),
        thread_id=_read_attr_text(message, "thread_id"),
        parent_id=_read_attr_text(message, "parent_id"),
        text=text,
        remote_image_keys=remote_image_keys,
        actionable=actionable,
    )
    LOGGER.info(
        "feishu inbound message event_id=%s message_id=%s chat_id=%s chat_type=%s root_id=%s thread_id=%s parent_id=%s actionable=%s text=%r",
        incoming_message.event_id,
        incoming_message.message_id,
        incoming_message.chat_id,
        incoming_message.chat_type,
        incoming_message.root_id,
        incoming_message.thread_id,
        incoming_message.parent_id,
        incoming_message.actionable,
        incoming_message.text,
    )
    return ParsedWebhook(type="message", message=incoming_message)


def parse_webhook_body(config: AppConfig, body: dict[str, Any]) -> ParsedWebhook:
    webhook_type = _read_text(body.get("type"))
    if webhook_type == "url_verification":
        return ParsedWebhook(type="challenge", challenge=_read_text(body.get("challenge")))

    header = body.get("header") if isinstance(body.get("header"), dict) else {}
    token = _read_text(body.get("token") or header.get("token") or body.get("event", {}).get("token") if isinstance(body.get("event"), dict) else "")
    if config.feishu.verify_token and token != config.feishu.verify_token:
        return ParsedWebhook(type="reject", status_code=403, body={"error": "invalid token"})
    event_type = _read_text(header.get("event_type") or body.get("event_type"))
    if event_type == "card.action.trigger":
        return parse_card_action_event(P2CardActionTrigger(body))
    if event_type != "im.message.receive_v1":
        return ParsedWebhook(type="ignore")
    return parse_message_event(config, P2ImMessageReceiveV1(body))


def split_text(text: str) -> list[str]:
    value = (text or "").strip()
    if not value:
        return []
    return [value[index:index + MAX_TEXT_CHUNK] for index in range(0, len(value), MAX_TEXT_CHUNK)]


def build_markdown_post_content(text: str) -> str:
    return _json_dumps({
        "zh_cn": {
            "content": [[{"tag": "md", "text": text}]],
        }
    })


def build_raw_request(uri: str, headers: dict[str, str], body: bytes) -> RawRequest:
    request = RawRequest()
    request.uri = uri
    request.headers = headers
    request.body = body
    return request
