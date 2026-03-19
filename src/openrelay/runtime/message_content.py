from __future__ import annotations

from openrelay.core import IncomingMessage
from openrelay.feishu.common import IMAGE_MESSAGE_PLACEHOLDER

DEFAULT_IMAGE_PROMPT = "用户发送了图片。请先查看图片内容，再根据图片直接回答用户。"


def message_summary_text(message: IncomingMessage) -> str:
    text = str(message.text or "").strip()
    if text:
        return text
    if message.local_image_paths:
        count = len(message.local_image_paths)
        return IMAGE_MESSAGE_PLACEHOLDER if count == 1 else f"{IMAGE_MESSAGE_PLACEHOLDER[:-1]} x{count}]"
    return ""


def build_backend_prompt(message: IncomingMessage) -> str:
    text = str(message.text or "").strip()
    if message.local_image_paths and text in {"", IMAGE_MESSAGE_PLACEHOLDER}:
        return DEFAULT_IMAGE_PROMPT
    return text
