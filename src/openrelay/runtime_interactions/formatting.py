from __future__ import annotations

import re
from typing import Any


MAX_ACTIONS_PER_ROW = 3


def chunk_actions(actions: list[dict[str, Any]], size: int = MAX_ACTIONS_PER_ROW) -> list[list[dict[str, Any]]]:
    return [actions[index : index + size] for index in range(0, len(actions), size)]


def normalize_text(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def shorten(value: object, max_length: int = 160) -> str:
    text = normalize_text(value)
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def format_permissions(permissions: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    file_system = permissions.get("fileSystem") if isinstance(permissions.get("fileSystem"), dict) else {}
    network = permissions.get("network") if isinstance(permissions.get("network"), dict) else {}
    macos = permissions.get("macos") if isinstance(permissions.get("macos"), dict) else {}
    read_paths = string_list(file_system.get("read"))
    write_paths = string_list(file_system.get("write"))
    if read_paths:
        lines.append("Read:")
        lines.extend(f"- `{path}`" for path in read_paths[:6])
        if len(read_paths) > 6:
            lines.append(f"- ... +{len(read_paths) - 6} more")
    if write_paths:
        lines.append("Write:")
        lines.extend(f"- `{path}`" for path in write_paths[:6])
        if len(write_paths) > 6:
            lines.append(f"- ... +{len(write_paths) - 6} more")
    if network.get("enabled") is True:
        lines.append("Network: enabled")
    if macos:
        lines.append("macOS permissions requested")
    return lines


def format_command_actions(command_actions: object) -> list[str]:
    if not isinstance(command_actions, list):
        return []
    lines: list[str] = []
    for action in command_actions[:6]:
        if not isinstance(action, dict):
            continue
        action_type = str(action.get("type") or "unknown")
        if action_type == "read":
            lines.append(f"Read `{action.get('path') or ''}`")
            continue
        if action_type == "listFiles":
            lines.append(f"List files in `{action.get('path') or ''}`")
            continue
        if action_type == "search":
            query = normalize_text(action.get("query"))
            path = normalize_text(action.get("path"))
            detail = query or path or normalize_text(action.get("command"))
            lines.append(f"Search {detail}".strip())
            continue
        lines.append(shorten(action.get("command") or action_type))
    return lines


def strip_code_fences(text: str) -> str:
    fenced = text.strip()
    if fenced.startswith("```") and fenced.endswith("```"):
        fenced = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", fenced)
        fenced = re.sub(r"\n?```$", "", fenced)
    return fenced.strip()


def normalize_decision_text(text: str) -> str:
    return re.sub(r"[^a-zA-Z\u4e00-\u9fff]+", "", text).casefold()
