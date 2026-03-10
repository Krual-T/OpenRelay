from __future__ import annotations

from typing import Any

from openrelay.card_actions import build_button
from openrelay.card_theme import build_card_shell



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
    directory_shortcuts = list(info.get("directory_shortcuts") or [])[:4]
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
                    *([f"> 上下文使用：`{info.get('context_usage')}`"] if info.get("context_usage") else []),
                    *([f"> 最近上下文：{info.get('context_preview')}"] if info.get("context_preview") else []),
                ]),
            },
        },
        {"tag": "action", "actions": [build_button("切到 main", "/main", "primary", action_context), build_button("切到 develop", "/develop", "default", action_context), build_button("会话列表", "/resume list", "default", action_context)]},
        {"tag": "action", "actions": [build_button("恢复上一条", "/resume latest", "default", action_context), build_button("新会话", "/new", "default", action_context), build_button("稳定版", "/stable", "default", action_context)]},
    ]

    if directory_shortcuts:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**常用目录**\n> 点击按钮会直接切到目标目录，并新建一个空会话。"}})
        shortcut_actions = [build_button(str(entry.get("label") or "目录"), str(entry.get("command") or "/cwd"), "default", action_context) for entry in directory_shortcuts]
        elements.append({"tag": "action", "actions": shortcut_actions})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join([f"> {entry.get('label')}: `{entry.get('display_path')}`" for entry in directory_shortcuts])}})

    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "> 想在指定目录进入 Codex：优先点上面的快捷目录；如果没有合适入口，再发送 `/cwd path/to/dir`。若要强制切回稳定可运行版本，发送 `/main 原因` 或 `/stable 原因`。"}})

    if sessions:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**最近会话**"}})
        for entry in sessions:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": _session_text(entry)}})
            elements.append({"tag": "action", "actions": [build_button("继续此会话" if entry.get("active") else "恢复此会话", f"/resume {entry.get('resume_token') or entry.get('session_id')}", "primary" if entry.get("active") else "default", action_context)]})

    elements.append({"tag": "action", "actions": [build_button("状态", "/status", "default", action_context), build_button("当前目录", "/cwd", "default", action_context), build_button("重启服务", "/restart", "default", action_context), build_button("帮助", "/help", "default", action_context)]})
    return build_card_shell("openrelay", elements, tone="info")
