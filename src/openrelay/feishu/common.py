from __future__ import annotations

import json
import logging
import mimetypes
from typing import Any

from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTrigger


MAX_TEXT_CHUNK = 3500
IMAGE_MESSAGE_PLACEHOLDER = "[图片]"
LOGGER = logging.getLogger("openrelay.feishu")


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
