from __future__ import annotations

from dataclasses import dataclass
import asyncio
import json
import re
import time
from typing import Any

import httpx

from openrelay.config import AppConfig
from openrelay.models import IncomingMessage


FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"
MAX_TEXT_CHUNK = 3500


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



def _read_text(value: object) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""



def _normalize_spaces(text: str) -> str:
    return " ".join(text.split())



def strip_mentions(text: str, mentions: list[dict[str, Any]] | None = None) -> str:
    output = str(text or "")
    for mention in mentions or []:
        key = _read_text(mention.get("key"))
        name = _read_text(mention.get("name"))
        if key:
            output = output.replace(key, " ")
        if name:
            output = output.replace(f"@{name}", " ")
    output = re.sub(r"<at\b[^>]*>.*?</at>", " ", output, flags=re.IGNORECASE | re.DOTALL)
    return _normalize_spaces(output)



def is_bot_mentioned(bot_open_id: str, mentions: list[dict[str, Any]] | None = None) -> bool:
    if not bot_open_id:
        return False
    for mention in mentions or []:
        mention_id = mention.get("id") if isinstance(mention, dict) else None
        if isinstance(mention_id, dict) and mention_id.get("open_id") == bot_open_id:
            return True
    return False



def parse_card_action_event(event: dict[str, Any]) -> ParsedWebhook:
    action = event.get("action") if isinstance(event.get("action"), dict) else {}
    value = action.get("value") if isinstance(action, dict) else {}
    text = ""
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, dict):
        text = _read_text(value.get("command") or value.get("text"))
    context = event.get("context") if isinstance(event.get("context"), dict) else {}
    chat_id = _read_text(context.get("chat_id") or context.get("open_chat_id") or event.get("operator", {}).get("open_id"))
    if not text or not chat_id:
        return ParsedWebhook(type="ignore")
    token = _read_text(event.get("token")) or f"card-{int(time.time())}"
    source_message_id = _read_text(context.get("open_message_id"))
    action_value = value if isinstance(value, dict) else {}
    return ParsedWebhook(
        type="message",
        message=IncomingMessage(
            event_id=f"card-action-{token}",
            message_id=source_message_id or f"card-action-{token}",
            reply_to_message_id=source_message_id,
            chat_id=chat_id,
            chat_type="group" if _read_text(context.get("chat_id")) else "p2p",
            sender_open_id=_read_text(event.get("operator", {}).get("open_id")),
            root_id=_read_text(action_value.get("root_id") or action_value.get("rootId")),
            thread_id=_read_text(action_value.get("thread_id") or action_value.get("threadId") or action_value.get("root_id") or action_value.get("rootId")),
            parent_id="",
            session_key=_read_text(action_value.get("session_key") or action_value.get("sessionKey")),
            session_owner_open_id=_read_text(action_value.get("session_owner_open_id") or action_value.get("sessionOwnerOpenId")),
            text=text,
            actionable=True,
        ),
    )



def parse_message_event(config: AppConfig, event: dict[str, Any]) -> ParsedWebhook:
    message = event.get("message") if isinstance(event, dict) else None
    if not isinstance(message, dict):
        return ParsedWebhook(type="ignore")
    if not _read_text(message.get("message_id")) or not _read_text(message.get("chat_id")):
        return ParsedWebhook(type="ignore")
    if message.get("message_type") != "text":
        return ParsedWebhook(type="ignore")
    content = _safe_json_loads(message.get("content"))
    mentions = message.get("mentions") if isinstance(message.get("mentions"), list) else []
    text = strip_mentions(_read_text(content.get("text")), mentions)
    chat_type = _read_text(message.get("chat_type")) or _read_text(event.get("chat", {}).get("chat_type") if isinstance(event.get("chat"), dict) else "") or "unknown"
    sender = event.get("sender") if isinstance(event, dict) else None
    sender_id = sender.get("sender_id") if isinstance(sender, dict) else None
    sender_open_id = _read_text(sender_id.get("open_id")) if isinstance(sender_id, dict) else ""
    actionable = chat_type == "p2p" or config.feishu.group_reply_all or is_bot_mentioned(config.feishu.bot_open_id, mentions)
    parsed = IncomingMessage(
        event_id=_read_text(message.get("message_id")),
        message_id=_read_text(message.get("message_id")),
        chat_id=_read_text(message.get("chat_id")),
        chat_type=chat_type,
        sender_open_id=sender_open_id,
        root_id=_read_text(message.get("root_id")),
        thread_id=_read_text(message.get("thread_id")),
        parent_id=_read_text(message.get("parent_id")),
        text=text,
        actionable=actionable,
    )
    return ParsedWebhook(type="message", message=parsed)



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
        parsed = parse_card_action_event(body.get("event") if isinstance(body.get("event"), dict) else {})
        if parsed.message is not None:
            parsed.message.event_id = _read_text(header.get("event_id")) or parsed.message.event_id
        return parsed
    if event_type != "im.message.receive_v1":
        return ParsedWebhook(type="ignore")
    parsed = parse_message_event(config, body.get("event") if isinstance(body.get("event"), dict) else {})
    if parsed.message is not None:
        parsed.message.event_id = _read_text(header.get("event_id")) or parsed.message.event_id
    return parsed



def split_text(text: str) -> list[str]:
    value = (text or "").strip()
    if not value:
        return []
    return [value[index:index + MAX_TEXT_CHUNK] for index in range(0, len(value), MAX_TEXT_CHUNK)]



def build_markdown_post_content(text: str) -> str:
    return json.dumps({
        "zh_cn": {
            "content": [[{"tag": "md", "text": text}]],
        }
    }, ensure_ascii=False)



def _api_ok(response: httpx.Response) -> bool:
    try:
        payload = response.json()
    except Exception:
        return False
    return response.is_success and payload.get("code") == 0



def _raise_api_error(response: httpx.Response) -> None:
    try:
        payload = response.json()
    except Exception:
        response.raise_for_status()
        raise RuntimeError("unexpected Feishu response")
    if not response.is_success:
        response.raise_for_status()
    if payload.get("code") != 0:
        raise RuntimeError(f"Feishu send failed: {payload}")


class FeishuMessenger:
    def __init__(self, config: AppConfig):
        self.config = config
        self._token_value = ""
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()
        self._client = httpx.AsyncClient(timeout=20.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_tenant_access_token(self) -> str:
        now = time.time()
        if self._token_value and now < self._token_expires_at:
            return self._token_value
        async with self._token_lock:
            now = time.time()
            if self._token_value and now < self._token_expires_at:
                return self._token_value
            response = await self._client.post(
                f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": self.config.feishu.app_id,
                    "app_secret": self.config.feishu.app_secret,
                },
            )
            response.raise_for_status()
            data = response.json()
            if data.get("code") != 0 or not _read_text(data.get("tenant_access_token")):
                raise RuntimeError(f"Feishu auth failed: {data}")
            self._token_value = _read_text(data.get("tenant_access_token"))
            expires_in = int(data.get("expire", 7200) or 7200)
            self._token_expires_at = time.time() + max(60, expires_in - 60)
            return self._token_value

    async def resolve_bot_open_id(self) -> str:
        token = await self.get_tenant_access_token()
        response = await self._client.get(
            f"{FEISHU_BASE_URL}/bot/v3/info",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        payload = response.json()
        bot_open_id = _read_text(payload.get("bot", {}).get("open_id") or payload.get("data", {}).get("bot", {}).get("open_id"))
        if not bot_open_id:
            raise RuntimeError(f"Feishu bot open_id missing: {payload}")
        self.config.feishu.bot_open_id = bot_open_id
        return bot_open_id

    async def send_text(self, chat_id: str, text: str, *, reply_to_message_id: str = "", root_id: str = "", force_new_message: bool = False) -> None:
        token = await self.get_tenant_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        for chunk in split_text(text):
            if reply_to_message_id and not force_new_message:
                try:
                    reply_response = await self._client.post(
                        f"{FEISHU_BASE_URL}/im/v1/messages/{reply_to_message_id}/reply",
                        headers=headers,
                        json={
                            "msg_type": "post",
                            "content": build_markdown_post_content(chunk),
                            "reply_in_thread": True,
                        },
                    )
                    if _api_ok(reply_response):
                        continue
                except Exception:
                    pass
            response = await self._client.post(
                f"{FEISHU_BASE_URL}/im/v1/messages",
                headers=headers,
                params={"receive_id_type": "chat_id"},
                json={
                    "receive_id": chat_id,
                    "msg_type": "post",
                    "content": build_markdown_post_content(chunk),
                    **({"root_id": root_id} if root_id else {}),
                },
            )
            _raise_api_error(response)

    async def send_interactive_card(self, chat_id: str, card: dict[str, Any], *, reply_to_message_id: str = "", root_id: str = "", force_new_message: bool = False) -> None:
        token = await self.get_tenant_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        content = json.dumps(card, ensure_ascii=False)
        if reply_to_message_id and not force_new_message:
            try:
                response = await self._client.post(
                    f"{FEISHU_BASE_URL}/im/v1/messages/{reply_to_message_id}/reply",
                    headers=headers,
                    json={
                        "content": content,
                        "msg_type": "interactive",
                        "reply_in_thread": True,
                    },
                )
                if _api_ok(response):
                    return
            except Exception:
                pass
        response = await self._client.post(
            f"{FEISHU_BASE_URL}/im/v1/messages",
            headers=headers,
            params={"receive_id_type": "chat_id"},
            json={
                "receive_id": chat_id,
                "content": content,
                "msg_type": "interactive",
                **({"root_id": root_id} if root_id else {}),
            },
        )
        _raise_api_error(response)
