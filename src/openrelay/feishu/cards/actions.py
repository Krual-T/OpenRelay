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


def build_interactive_container(
    title: str,
    description: str,
    command: str,
    *,
    context: dict[str, str] | None = None,
    border_color: str = "grey",
    background_style: str = "default",
    disabled: bool = False,
    disabled_tip: str = "",
) -> dict[str, Any]:
    container: dict[str, Any] = {
        "tag": "interactive_container",
        "width": "fill",
        "height": "auto",
        "direction": "vertical",
        "horizontal_align": "left",
        "vertical_align": "center",
        "vertical_spacing": "4px",
        "background_style": background_style,
        "has_border": True,
        "border_color": border_color,
        "corner_radius": "12px",
        "padding": "10px 12px 10px 12px",
        "disabled": disabled,
        "elements": [
            {
                "tag": "markdown",
                "content": "\n".join(part for part in [f"**{title}**", description.strip()] if part),
            }
        ],
    }
    if disabled:
        if disabled_tip:
            container["disabled_tips"] = {"tag": "plain_text", "content": disabled_tip}
    else:
        container["behaviors"] = [{"type": "callback", "value": build_button_value(command, context or {})}]
    return container
