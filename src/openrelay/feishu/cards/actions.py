from __future__ import annotations

from typing import Any


ACTION_CONTEXT_KEYS = ["rootId", "threadId", "sessionKey", "sessionOwnerOpenId"]


def build_button_value(command: str, context: dict[str, str]) -> dict[str, str]:
    value = {"command": command}
    for key in ACTION_CONTEXT_KEYS:
        entry = str(context.get(key) or "").strip()
        if entry:
            value[key] = entry
    return value


def build_button(label: str, command: str, button_type: str = "default", context: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "tag": "button",
        "type": button_type,
        "text": {"tag": "plain_text", "content": label},
        "value": build_button_value(command, context or {}),
    }


def build_command_value(command: str, context: dict[str, str]) -> dict[str, str]:
    return build_button_value(command, context)


def build_command_button(label: str, command: str, button_type: str = "default", context: dict[str, str] | None = None) -> dict[str, Any]:
    return build_button(label, command, button_type, context)
