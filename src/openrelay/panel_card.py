from __future__ import annotations

from typing import Any

from openrelay.card_actions import build_button
from openrelay.card_theme import build_card_shell


PANEL_HOME = "home"
PANEL_SESSIONS = "sessions"
PANEL_DIRECTORIES = "directories"
PANEL_COMMANDS = "commands"
PANEL_STATUS = "status"

PANEL_VIEW_LABELS = {
    PANEL_HOME: "总览",
    PANEL_SESSIONS: "会话",
    PANEL_DIRECTORIES: "目录",
    PANEL_COMMANDS: "命令",
    PANEL_STATUS: "状态",
}

SESSION_SORT_LABELS = {
    "updated-desc": "最近更新优先",
    "active-first": "当前会话优先",
}


def _markdown(content: str) -> dict[str, Any]:
    return {"tag": "div", "text": {"tag": "lark_md", "content": content}}



def _action_row(actions: list[dict[str, Any]]) -> dict[str, Any]:
    return {"tag": "action", "actions": actions}



def _result_block(title: str, meta: str = "", preview: str = "") -> dict[str, Any]:
    lines = [f"**{title}**"]
    if meta:
        lines.append(f"> {meta}")
    if preview:
        lines.append(f"> {preview}")
    return _markdown("\n".join(lines))



def _append_session_items(elements: list[dict[str, Any]], sessions: list[dict[str, Any]], action_context: dict[str, str]) -> None:
    if not sessions:
        elements.append(_markdown("> 还没有可恢复的历史会话。"))
        return
    for entry in sessions:
        index = entry.get("index", "-")
        title = str(entry.get("title") or entry.get("label") or entry.get("session_id") or "未命名会话")
        heading = f"{index}. {title}{' · 当前' if entry.get('active') else ''}"
        preview = str(entry.get("preview") or "").strip()
        elements.append(_result_block(heading, str(entry.get("meta") or ""), f"预览：{preview}" if preview else ""))
        resume_token = str(entry.get("resume_token") or entry.get("session_id") or "")
        if resume_token:
            elements.append(
                _action_row(
                    [
                        build_button(
                            "继续此会话" if entry.get("active") else "恢复此会话",
                            f"/resume {resume_token}",
                            "primary" if entry.get("active") else "default",
                            action_context,
                        )
                    ]
                )
            )



def _append_directory_items(elements: list[dict[str, Any]], shortcuts: list[dict[str, Any]], action_context: dict[str, str]) -> None:
    if not shortcuts:
        elements.append(_markdown("> 当前没有可用的快捷目录入口。"))
        return
    for entry in shortcuts:
        label = str(entry.get("label") or "目录")
        display_path = str(entry.get("display_path") or entry.get("path") or ".")
        command = str(entry.get("command") or "/cwd")
        elements.append(_result_block(label, f"目录 `{display_path}`", "点击后会新建一个空会话，并直接切到目标目录。"))
        elements.append(_action_row([build_button("切到此目录", command, "default", action_context)]))



def _append_generic_items(elements: list[dict[str, Any]], items: list[dict[str, Any]], action_context: dict[str, str]) -> None:
    if not items:
        elements.append(_markdown("> 暂无结果。"))
        return
    for entry in items:
        title = str(entry.get("title") or "未命名项")
        meta = str(entry.get("meta") or "")
        preview = str(entry.get("preview") or "")
        command = str(entry.get("command") or "")
        action_label = str(entry.get("action_label") or "执行")
        action_type = str(entry.get("action_type") or "default")
        elements.append(_result_block(title, meta, preview))
        if command:
            elements.append(_action_row([build_button(action_label, command, action_type, action_context)]))



def _append_view_nav(elements: list[dict[str, Any]], current_view: str, action_context: dict[str, str]) -> None:
    rows = [
        [("总览", "/panel", PANEL_HOME), ("会话", "/panel sessions", PANEL_SESSIONS), ("目录", "/panel directories", PANEL_DIRECTORIES)],
        [("命令", "/panel commands", PANEL_COMMANDS), ("状态", "/panel status", PANEL_STATUS), ("帮助", "/help", "help")],
    ]
    for row in rows:
        elements.append(
            _action_row(
                [
                    build_button(label, command, "primary" if current_view == view_key else "default", action_context)
                    for label, command, view_key in row
                ]
            )
        )



def _build_header_block(info: dict[str, Any], view: str) -> dict[str, Any]:
    current_title = str(info.get("current_title") or "未命名会话")
    session_id = str(info.get("session_id") or "-")
    cwd = str(info.get("cwd") or ".")
    model = str(info.get("model") or "-")
    provider = str(info.get("provider") or "-")
    sandbox = str(info.get("sandbox") or "-")
    channel = str(info.get("channel") or "main（稳定）")
    lines = [
        f"**面板 · {PANEL_VIEW_LABELS.get(view, '总览')}**",
        f"> 当前会话：{current_title}",
        f"> ID：`{session_id}`",
        f"> 通道：`{channel}`",
        f"> 目录：`{cwd}`",
        f"> 模型：`{model}` · Provider：`{provider}`",
        f"> Sandbox：`{sandbox}`",
    ]
    if info.get("context_usage"):
        lines.append(f"> 上下文使用：`{info.get('context_usage')}`")
    if info.get("context_preview"):
        lines.append(f"> 最近上下文：{info.get('context_preview')}")
    if view == PANEL_HOME:
        lines.append("> 角色：总入口。先选会话 / 目录 / 命令 / 状态，再进入对应结果面。")
    elif view == PANEL_SESSIONS:
        sort_mode = str(info.get("sort_mode") or "updated-desc")
        lines.append(f"> 结果：第 `{info.get('page', 1)}` / `{info.get('total_pages', 1)}` 页 · 排序：`{SESSION_SORT_LABELS.get(sort_mode, sort_mode)}`")
        lines.append("> 语义：会话结果继续复用 `/resume` 主路径，卡片只负责更快浏览。")
    elif view == PANEL_DIRECTORIES:
        lines.append(f"> 结果：`{len(list(info.get('directory_shortcuts') or []))}` 个目录入口")
        lines.append("> 语义：优先点快捷目录；没有合适入口时再手写 `/cwd <path>`。")
    elif view == PANEL_COMMANDS:
        lines.append(f"> 结果：`{len(list(info.get('command_entries') or []))}` 个高频动作")
        lines.append("> 语义：只保留高频命令，减少在帮助文案和命令记忆之间来回切换。")
    elif view == PANEL_STATUS:
        lines.append("> 语义：先看现场，再决定继续当前任务、切目录，还是切会话。")
    return _markdown("\n".join(lines))



def _build_home_card(info: dict[str, Any]) -> dict[str, Any]:
    action_context = info.get("action_context") if isinstance(info.get("action_context"), dict) else {}
    sessions = list(info.get("sessions") or [])[:3]
    shortcuts = list(info.get("directory_shortcuts") or [])[:3]
    elements: list[dict[str, Any]] = [_build_header_block(info, PANEL_HOME)]
    _append_view_nav(elements, PANEL_HOME, action_context)
    elements.append(_markdown("**进入哪一类结果**\n> 这四个入口分别收敛会话、目录、命令和状态结果；下面的预览和结果页使用同一套项目语义。"))
    elements.append(_action_row([build_button("恢复上一条", "/resume latest", "primary", action_context), build_button("新会话", "/new", "default", action_context), build_button("当前状态", "/panel status", "default", action_context)]))
    elements.append(_markdown("**最近会话**\n> 想继续旧任务时，优先先看这里；如果不够，再切到完整会话结果页。"))
    _append_session_items(elements, sessions, action_context)
    elements.append(_action_row([build_button("全部会话", "/panel sessions", "default", action_context), build_button("命令式列表", "/resume list", "default", action_context), build_button("帮助", "/help", "default", action_context)]))
    elements.append(_markdown("**目录入口**\n> 目录预览与目录结果页共用同一套入口语义；点击后都会复用 `/cwd` 主路径。"))
    _append_directory_items(elements, shortcuts, action_context)
    elements.append(_action_row([build_button("当前目录", "/cwd", "default", action_context), build_button("切到 main", "/main", "default", action_context), build_button("切到 develop", "/develop", "default", action_context)]))
    return build_card_shell("openrelay panel", elements, tone="info")



def _build_sessions_card(info: dict[str, Any]) -> dict[str, Any]:
    action_context = info.get("action_context") if isinstance(info.get("action_context"), dict) else {}
    page = int(info.get("page") or 1)
    total_pages = int(info.get("total_pages") or 1)
    sort_mode = str(info.get("sort_mode") or "updated-desc")
    elements: list[dict[str, Any]] = [_build_header_block(info, PANEL_SESSIONS)]
    _append_view_nav(elements, PANEL_SESSIONS, action_context)
    elements.append(_markdown("**会话结果**\n> 先在这里排序或翻页，再决定恢复哪条会话；真正执行仍统一走 `/resume`。"))
    elements.append(_action_row([
        build_button("最近更新", "/panel sessions --page 1 --sort updated-desc", "primary" if sort_mode == "updated-desc" else "default", action_context),
        build_button("当前优先", "/panel sessions --page 1 --sort active-first", "primary" if sort_mode == "active-first" else "default", action_context),
        build_button("恢复上一条", "/resume latest", "default", action_context),
    ]))
    page_actions = [build_button("命令式列表", f"/resume list --page {page} --sort {sort_mode}", "default", action_context)]
    if page > 1:
        page_actions.insert(0, build_button("上一页", f"/panel sessions --page {page - 1} --sort {sort_mode}", "default", action_context))
    if page < total_pages:
        page_actions.append(build_button("下一页", f"/panel sessions --page {page + 1} --sort {sort_mode}", "default", action_context))
    elements.append(_action_row(page_actions))
    _append_session_items(elements, list(info.get("sessions") or []), action_context)
    return build_card_shell("openrelay panel", elements, tone="info")



def _build_directories_card(info: dict[str, Any]) -> dict[str, Any]:
    action_context = info.get("action_context") if isinstance(info.get("action_context"), dict) else {}
    shortcuts = list(info.get("directory_shortcuts") or [])
    elements: list[dict[str, Any]] = [_build_header_block(info, PANEL_DIRECTORIES)]
    _append_view_nav(elements, PANEL_DIRECTORIES, action_context)
    elements.append(_markdown("**目录结果**\n> 优先使用稳定快捷入口；没有合适入口时，再手写 `/cwd <path>`。"))
    _append_directory_items(elements, shortcuts, action_context)
    elements.append(_action_row([build_button("当前目录", "/cwd", "default", action_context), build_button("切到 main", "/main", "default", action_context), build_button("切到 develop", "/develop", "default", action_context)]))
    return build_card_shell("openrelay panel", elements, tone="info")



def _build_commands_card(info: dict[str, Any]) -> dict[str, Any]:
    action_context = info.get("action_context") if isinstance(info.get("action_context"), dict) else {}
    elements: list[dict[str, Any]] = [_build_header_block(info, PANEL_COMMANDS)]
    _append_view_nav(elements, PANEL_COMMANDS, action_context)
    elements.append(_markdown("**命令结果**\n> 这里保留的是高频动作，不是完整命令清单；目标是更快进入下一步。"))
    _append_generic_items(elements, list(info.get("command_entries") or []), action_context)
    return build_card_shell("openrelay panel", elements, tone="info")



def _build_status_card(info: dict[str, Any]) -> dict[str, Any]:
    action_context = info.get("action_context") if isinstance(info.get("action_context"), dict) else {}
    elements: list[dict[str, Any]] = [_build_header_block(info, PANEL_STATUS)]
    _append_view_nav(elements, PANEL_STATUS, action_context)
    elements.append(_markdown("**状态结果**\n> 先判断现场，再决定是继续发消息、切目录，还是切去旧会话。"))
    _append_generic_items(elements, list(info.get("status_entries") or []), action_context)
    elements.append(_action_row([build_button("完整状态", "/status", "primary", action_context), build_button("用量", "/usage", "default", action_context), build_button("帮助", "/help", "default", action_context)]))
    return build_card_shell("openrelay panel", elements, tone="info")



def build_panel_card(info: dict[str, Any]) -> dict[str, Any]:
    view = str(info.get("view") or PANEL_HOME)
    if view == PANEL_SESSIONS:
        return _build_sessions_card(info)
    if view == PANEL_DIRECTORIES:
        return _build_directories_card(info)
    if view == PANEL_COMMANDS:
        return _build_commands_card(info)
    if view == PANEL_STATUS:
        return _build_status_card(info)
    return _build_home_card(info)
