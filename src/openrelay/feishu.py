from __future__ import annotations

from dataclasses import dataclass, replace
import asyncio
import json
import mimetypes
import re
import logging
from pathlib import Path
import tempfile
import uuid
from typing import Any, Awaitable, Callable

import lark_oapi as lark
from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody, UpdateMessageRequest, UpdateMessageRequestBody
from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1
from lark_oapi.core.enum import AccessTokenType, HttpMethod, LogLevel
from lark_oapi.core.model import BaseRequest, RawRequest
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTrigger, P2CardActionTriggerResponse

from openrelay.config import AppConfig
from openrelay.models import IncomingMessage


MAX_TEXT_CHUNK = 3500
IMAGE_MESSAGE_PLACEHOLDER = "[图片]"
LOGGER = logging.getLogger("openrelay.feishu")


@dataclass(slots=True)
class ParsedWebhook:
    type: str
    challenge: str = ""
    status_code: int = 200
    body: dict[str, Any] | None = None
    message: IncomingMessage | None = None



def _safe_json_loads(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _dedupe_preserve_order(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = value.strip() if isinstance(value, str) else ""
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


def _collect_post_message_parts(node: object, texts: list[str], image_keys: list[str]) -> None:
    if isinstance(node, list):
        for item in node:
            _collect_post_message_parts(item, texts, image_keys)
        return
    if not isinstance(node, dict):
        return

    tag = _read_text(node.get("tag")).lower()
    if tag == "img":
        image_key = _read_text(node.get("image_key"))
        if image_key:
            image_keys.append(image_key)
    elif tag in {"text", "a", "at"}:
        text = _read_text(node.get("text"))
        if text:
            texts.append(text)

    title = _read_text(node.get("title"))
    if title:
        texts.append(title)

    for value in node.values():
        if isinstance(value, (dict, list)):
            _collect_post_message_parts(value, texts, image_keys)


def _extract_post_message_content(content: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    texts: list[str] = []
    image_keys: list[str] = []
    _collect_post_message_parts(content, texts, image_keys)
    return _normalize_spaces(" ".join(texts)), _dedupe_preserve_order(image_keys)



def _read_text(value: object) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""



def _normalize_spaces(text: str) -> str:
    return " ".join(text.split())



def _read_attr_text(value: object, name: str) -> str:
    if isinstance(value, dict):
        return _read_text(value.get(name))
    return _read_text(getattr(value, name, ""))



def _read_nested_attr_text(value: object, name: str, nested: str) -> str:
    if isinstance(value, dict):
        inner = value.get(name)
    else:
        inner = getattr(value, name, None)
    return _read_attr_text(inner, nested)



def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)



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



def _event_header_attr(event: object, name: str) -> str:
    header = getattr(event, "header", None)
    return _read_attr_text(header, name)



def _coerce_message_event(event: dict[str, Any] | P2ImMessageReceiveV1) -> P2ImMessageReceiveV1:
    if isinstance(event, P2ImMessageReceiveV1):
        return event
    payload = event if "event" in event else {"event": event}
    return P2ImMessageReceiveV1(payload)



def _coerce_card_action_event(event: dict[str, Any] | P2CardActionTrigger) -> P2CardActionTrigger:
    if isinstance(event, P2CardActionTrigger):
        return event
    payload = event if "event" in event else {"event": event}
    return P2CardActionTrigger(payload)



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
    token = _read_attr_text(event_data, "token") or f"card-{uuid.uuid4().hex[:12]}"
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
    return ParsedWebhook(
        type="message",
        message=IncomingMessage(
            event_id=_event_header_attr(sdk_event, "event_id") or _read_attr_text(message, "message_id"),
            message_id=_read_attr_text(message, "message_id"),
            chat_id=_read_attr_text(message, "chat_id"),
            chat_type=chat_type,
            sender_open_id=sender_open_id,
            root_id=_read_attr_text(message, "root_id"),
            thread_id=_read_attr_text(message, "thread_id"),
            parent_id=_read_attr_text(message, "parent_id"),
            text=text,
            remote_image_keys=remote_image_keys,
            actionable=actionable,
        ),
    )



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



def _response_payload(response: object) -> dict[str, Any]:
    raw = getattr(response, "raw", None)
    if raw is None or getattr(raw, "content", None) is None:
        return {}
    try:
        return json.loads(bytes(raw.content).decode("utf-8"))
    except Exception:
        return {}


def _response_bytes(response: object) -> bytes:
    raw = getattr(response, "raw", None)
    if raw is None or getattr(raw, "content", None) is None:
        return b""
    return bytes(raw.content)


def _response_headers(response: object) -> dict[str, str]:
    raw = getattr(response, "raw", None)
    headers = getattr(raw, "headers", None) if raw is not None else None
    if isinstance(headers, dict):
        return {str(key).lower(): str(value) for key, value in headers.items()}
    try:
        return {str(key).lower(): str(value) for key, value in dict(headers or {}).items()}
    except Exception:
        return {}


def _guess_file_suffix(content_type: str) -> str:
    guessed = mimetypes.guess_extension(content_type or "", strict=False) or ""
    return guessed if guessed else ".img"



def _ensure_success(response: object, label: str) -> None:
    if hasattr(response, "success") and response.success():
        return
    payload = _response_payload(response)
    code = getattr(response, "code", None)
    message = _read_text(getattr(response, "msg", "")) or _read_text(payload.get("msg")) or _json_dumps(payload) or "unknown error"
    raise RuntimeError(f"{label} failed: code={code} msg={message}")



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
        request = ReplyMessageRequest.builder().message_id(message_id).request_body(
            ReplyMessageRequestBody.builder().msg_type(msg_type).content(content).reply_in_thread(reply_in_thread).uuid(uuid.uuid4().hex).build()
        ).build()
        response = await self.client.im.v1.message.areply(request)
        _ensure_success(response, f"Feishu reply {msg_type}")
        return _response_payload(response)

    async def create_message(self, chat_id: str, msg_type: str, content: str, *, root_id: str = "") -> dict[str, Any]:
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
        request = UpdateMessageRequest.builder().message_id(message_id).request_body(
            UpdateMessageRequestBody.builder().msg_type(msg_type).content(content).build()
        ).build()
        response = await self.client.im.v1.message.aupdate(request)
        _ensure_success(response, f"Feishu update {msg_type}")
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
    ) -> tuple[str, ...]:
        message_ids: list[str] = []
        for chunk in split_text(text):
            if reply_to_message_id and not force_new_message:
                try:
                    payload = await self.reply_message(
                        reply_to_message_id,
                        "post",
                        build_markdown_post_content(chunk),
                        reply_in_thread=True,
                    )
                    message_id = _read_text(payload.get("data", {}).get("message_id"))
                    if message_id:
                        message_ids.append(message_id)
                    continue
                except Exception:
                    LOGGER.exception("reply text failed for message_id=%s", reply_to_message_id)
            payload = await self.create_message(chat_id, "post", build_markdown_post_content(chunk), root_id=root_id)
            message_id = _read_text(payload.get("data", {}).get("message_id"))
            if message_id:
                message_ids.append(message_id)
        return tuple(message_ids)

    async def send_interactive_card(
        self,
        chat_id: str,
        card: dict[str, Any],
        *,
        reply_to_message_id: str = "",
        root_id: str = "",
        force_new_message: bool = False,
        update_message_id: str = "",
    ) -> str:
        content = _json_dumps(card)
        if update_message_id:
            try:
                await self.update_message(update_message_id, "interactive", content)
                return update_message_id
            except Exception:
                LOGGER.exception("update interactive card failed for message_id=%s", update_message_id)
        if reply_to_message_id and not force_new_message:
            try:
                payload = await self.reply_message(reply_to_message_id, "interactive", content, reply_in_thread=True)
                return _read_text(payload.get("data", {}).get("message_id"))
            except Exception:
                LOGGER.exception("reply interactive card failed for message_id=%s", reply_to_message_id)
        payload = await self.create_message(chat_id, "interactive", content, root_id=root_id)
        return _read_text(payload.get("data", {}).get("message_id"))



class FeishuEventDispatcher:
    def __init__(
        self,
        config: AppConfig,
        loop: asyncio.AbstractEventLoop,
        dispatch_message: Callable[[IncomingMessage], Awaitable[None]],
        messenger: FeishuMessenger | None = None,
        log: logging.Logger | None = None,
    ):
        self.config = config
        self.loop = loop
        self.dispatch_message = dispatch_message
        self.messenger = messenger
        self.logger = log or LOGGER

    def build(self) -> lark.EventDispatcherHandler:
        builder = lark.EventDispatcherHandler.builder(self.config.feishu.encrypt_key, self.config.feishu.verify_token, LogLevel.INFO)
        builder.register_p2_im_message_receive_v1(self._handle_message_event)
        builder.register_p2_card_action_trigger(self._handle_card_action)
        return builder.build()

    async def _dispatch_with_media_resolution(self, message: IncomingMessage) -> None:
        if self.messenger is not None and message.remote_image_keys:
            local_image_paths: list[str] = []
            for image_key in message.remote_image_keys:
                try:
                    image_path = await self.messenger.download_message_resource_to_file(message.message_id, image_key, resource_type="image")
                except Exception:
                    self.logger.exception(
                        "failed to download inbound Feishu image message_id=%s image_key=%s",
                        message.message_id,
                        image_key,
                    )
                    continue
                local_image_paths.append(image_path)
            if local_image_paths:
                message = replace(message, remote_image_keys=(), local_image_paths=tuple(local_image_paths))
        await self.dispatch_message(message)

    def _schedule(self, message: IncomingMessage) -> None:
        self.loop.call_soon_threadsafe(lambda: asyncio.create_task(self._dispatch_with_media_resolution(message)))

    def _handle_message_event(self, event: P2ImMessageReceiveV1) -> None:
        parsed = parse_message_event(self.config, event)
        if parsed.type == "message" and parsed.message is not None:
            self._schedule(parsed.message)

    def _handle_card_action(self, event: P2CardActionTrigger) -> P2CardActionTriggerResponse:
        parsed = parse_card_action_event(event)
        if parsed.type == "message" and parsed.message is not None:
            self._schedule(parsed.message)
        return P2CardActionTriggerResponse()
