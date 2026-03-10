from __future__ import annotations

from typing import Any

from openrelay.card_actions import build_button
from openrelay.card_theme import build_card_shell
from openrelay.session_browser import SESSION_SORT_ACTIVE, SESSION_SORT_UPDATED


def build_resume_list_command(target: str = "list", *, page: int = 1, sort_mode: str = SESSION_SORT_UPDATED) -> str:
    parts = ["/resume"]
    if target:
        parts.append(target)
    parts.extend(["--page", str(max(page, 1)), "--sort", sort_mode])
    return " ".join(parts)


def _session_text(entry: dict[str, Any]) -> str:
    title = str(entry.get("title") or entry.get("label") or entry.get("session_id") or "未命名会话")
    lines = [f"**{entry.get('index', '-')}. {title}**{' · 当前' if entry.get('active') else ''}"]
    if entry.get("meta"):
        lines.append(f"> {entry['meta']}")
    if entry.get("preview"):
        lines.append(f"> 预览：{entry['preview']}")
    return "\n".join(lines)


def build_session_list_card(info: dict[str, Any]) -> dict[str, Any]:
    sessions = list(info.get("sessions") or [])
    action_context = info.get("action_context") if isinstance(info.get("action_context"), dict) else {}
    page = int(info.get("page") or 1)
    sort_mode = str(info.get("sort_mode") or SESSION_SORT_UPDATED)
    has_previous = bool(info.get("has_previous"))
    has_next = bool(info.get("has_next"))
    current_title = str(info.get("current_title") or "未命名会话")
    current_session_id = str(info.get("current_session_id") or "-")

    sort_label = "最近更新优先" if sort_mode == SESSION_SORT_UPDATED else "当前会话优先"
    next_sort = SESSION_SORT_ACTIVE if sort_mode == SESSION_SORT_UPDATED else SESSION_SORT_UPDATED
    next_sort_label = "切到当前优先" if sort_mode == SESSION_SORT_UPDATED else "切到最近更新"

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join(
                    [
                        "**会话列表**",
                        f"> 当前会话：{current_title}",
                        f"> session_id：`{current_session_id}`",
                        f"> 排序：`{sort_label}` · 第 `{page}` 页",
                        "> 点击按钮即可恢复；也可以继续手动输入 `/resume <编号|session_id|latest>`。",
                    ]
                ),
            },
        }
    ]

    if sessions:
        for entry in sessions:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": _session_text(entry)}})
            elements.append(
                {
                    "tag": "action",
                    "actions": [
                        build_button(
                            "继续此会话" if entry.get("active") else "恢复此会话",
                            build_resume_list_command(
                                str(entry.get("resume_token") or entry.get("session_id") or ""),
                                page=page,
                                sort_mode=sort_mode,
                            ),
                            "primary" if entry.get("active") else "default",
                            action_context,
                        )
                    ],
                }
            )
    else:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "> 当前没有可恢复的会话。"}})

    controls = [build_button(next_sort_label, build_resume_list_command("list", page=1, sort_mode=next_sort), "default", action_context)]
    if has_previous:
        controls.insert(0, build_button("上一页", build_resume_list_command("list", page=page - 1, sort_mode=sort_mode), "default", action_context))
    if has_next:
        controls.append(build_button("下一页", build_resume_list_command("list", page=page + 1, sort_mode=sort_mode), "primary", action_context))
    elements.append({"tag": "action", "actions": controls})
    elements.append({"tag": "action", "actions": [build_button("恢复上一条", build_resume_list_command("latest", page=page, sort_mode=sort_mode), "default", action_context), build_button("面板", "/panel", "default", action_context), build_button("帮助", "/help", "default", action_context)]})

    return build_card_shell("openrelay sessions", elements, tone="info")
