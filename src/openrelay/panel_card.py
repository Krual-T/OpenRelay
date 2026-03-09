from __future__ import annotations

from typing import Any



def _build_button_value(command: str, context: dict[str, str]) -> dict[str, str]:
    value = {"command": command}
    for key in ["rootId", "threadId", "sessionKey", "sessionOwnerOpenId"]:
        entry = str(context.get(key) or "").strip()
        if entry:
            value[key] = entry
    return value



def _button(label: str, command: str, button_type: str = "default", context: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "tag": "button",
        "type": button_type,
        "text": {"tag": "plain_text", "content": label},
        "value": _build_button_value(command, context or {}),
    }



def _session_text(entry: dict[str, Any]) -> str:
    title = str(entry.get("title") or entry.get("label") or entry.get("session_id") or "未命名会话")
    lines = [f"**{entry.get('index', '-')}. {title}**{' · 当前' if entry.get('active') else ''}"]
    if entry.get("meta"):
        lines.append(f"> {entry['meta']}")
    if entry.get("preview"):
        lines.append(f"> 预览：{entry['preview']}")
    return "\n".join(lines)



def build_panel_card(info: dict[str, Any]) -> dict[str, Any]:
    session_id = str(info.get("session_id") or "-")
    current_title = str(info.get("current_title") or "未命名会话")
    cwd = str(info.get("cwd") or ".")
    model = str(info.get("model") or "-")
    provider = str(info.get("provider") or "-")
    sandbox = str(info.get("sandbox") or "-")
    channel = str(info.get("channel") or "main（稳定）")
    sessions = list(info.get("sessions") or [])[:5]
    action_context = info.get("action_context") if isinstance(info.get("action_context"), dict) else {}

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join([
                    "**当前会话**",
                    f"> 名称：{current_title}",
                    f"> ID：`{session_id}`",
                    f"> 通道：`{channel}`",
                    f"> 目录：`{cwd}`",
                    f"> 模型：`{model}` · Provider：`{provider}`",
                    f"> Sandbox：`{sandbox}`",
                    *([f"> 上下文使用：`{info.get('context_usage')}`" ] if info.get("context_usage") else []),
                    *([f"> 最近上下文：{info.get('context_preview')}" ] if info.get("context_preview") else []),
                ]),
            },
        },
        {"tag": "action", "actions": [_button("切到 main", "/main", "primary", action_context), _button("切到 develop", "/develop", "default", action_context), _button("会话列表", "/resume", "default", action_context)]},
        {"tag": "action", "actions": [_button("恢复上一条", "/resume latest", "default", action_context), _button("新会话", "/new", "default", action_context), _button("稳定版", "/stable", "default", action_context)]},
        {"tag": "div", "text": {"tag": "lark_md", "content": "> 想在指定目录进入 Codex：先发送 `/cwd path/to/dir`，再发消息；若要强制切回稳定可运行版本，发送 `/main 原因` 或 `/stable 原因`。"}},
    ]

    if sessions:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**最近会话**"}})
        for entry in sessions:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": _session_text(entry)}})
            elements.append({"tag": "action", "actions": [_button("继续此会话" if entry.get("active") else "恢复此会话", f"/resume {entry.get('session_id')}", "primary" if entry.get("active") else "default", action_context)]})

    elements.append({"tag": "action", "actions": [_button("状态", "/status", "default", action_context), _button("当前目录", "/cwd", "default", action_context), _button("重启服务", "/restart", "default", action_context), _button("帮助", "/help", "default", action_context)]})
    return {
        "config": {"wide_screen_mode": True, "enable_forward": True, "update_multi": True},
        "header": {"template": "blue", "title": {"tag": "plain_text", "content": "openrelay"}},
        "elements": elements,
    }
