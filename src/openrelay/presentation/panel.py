from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
import shlex

from openrelay.backends import BackendDescriptor
from openrelay.core import AppConfig, IncomingMessage, SessionRecord, format_release_channel, infer_release_channel
from openrelay.feishu.cards import build_button, build_card_shell, build_interactive_container, build_note_bar, build_status_hero, divider_block, markdown_block
from openrelay.session.browser import SessionBrowser, SessionSortMode
from openrelay.session.shortcuts import SessionShortcutService
from openrelay.session.workspace import SessionWorkspaceService

from .session import SessionPresentation, build_session_list_card

if TYPE_CHECKING:
    from openrelay.runtime.commands import PanelCommandArgs


PANEL_HOME = "home"
PANEL_SESSIONS = "sessions"
PANEL_WORKSPACE = "workspace"
PANEL_COMMANDS = "commands"
PANEL_STATUS = "status"

PANEL_VIEW_LABELS = {
    PANEL_HOME: "总览",
    PANEL_SESSIONS: "会话",
    PANEL_WORKSPACE: "工作区",
    PANEL_COMMANDS: "命令",
    PANEL_STATUS: "状态",
}

SESSION_SORT_LABELS = {
    "updated-desc": "最近更新优先",
    "active-first": "当前会话优先",
}


def _page_window(page: int, known_page_count: int, width: int = 5) -> list[int]:
    if known_page_count <= 0:
        return []
    current = max(page, 1)
    size = max(width, 1)
    start = max(1, current - (size // 2))
    end = min(known_page_count, start + size - 1)
    start = max(1, end - size + 1)
    return list(range(start, end + 1))


def _markdown(content: str) -> dict[str, Any]:
    return markdown_block(content)


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
        elements.append(_markdown("> 当前没有可用的快捷工作区入口。"))
        return
    for entry in shortcuts:
        label = str(entry.get("label") or "目录")
        display_path = str(entry.get("display_path") or entry.get("path") or ".")
        command = str(entry.get("command") or "/workspace")
        elements.append(_result_block(label, f"目录 `{display_path}`", "点击后会清空当前 scope，并把下一条真实消息放到目标目录执行。"))
        elements.append(_action_row([build_button("进入此目录", command, "default", action_context)]))


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
        [("总览", "/panel", PANEL_HOME), ("会话", "/panel sessions", PANEL_SESSIONS), ("工作区", "/panel workspace", PANEL_WORKSPACE)],
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


def build_panel_card(info: dict[str, Any]) -> dict[str, Any]:
    view = str(info.get("view") or PANEL_HOME)
    if view == PANEL_SESSIONS:
        return _build_sessions_card(info)
    if view == PANEL_WORKSPACE:
        return _build_workspace_card(info)
    if view == PANEL_COMMANDS:
        return _build_commands_card(info)
    if view == PANEL_STATUS:
        return _build_status_card(info)
    return _build_home_card(info)


def _build_header_elements(info: dict[str, Any], view: str) -> list[dict[str, Any]]:
    current_title = str(info.get("current_title") or "未命名会话")
    session_id = str(info.get("session_id") or "-")
    cwd = str(info.get("cwd") or ".")
    model = str(info.get("model") or "-")
    provider = str(info.get("provider") or "-")
    sandbox = str(info.get("sandbox") or "-")
    channel = str(info.get("channel") or "main（稳定）")
    summary = "从卡片按钮进入结果面、翻页或返回总览时，优先原地更新当前卡片。"
    if view == PANEL_HOME:
        summary = "总入口。先选会话 / 工作区 / 命令 / 状态，再进入对应结果面。"
    elif view == PANEL_SESSIONS:
        sort_mode = str(info.get("sort_mode") or "updated-desc")
        summary = (
            f"结果：第 `{info.get('page', 1)}` / `{info.get('total_pages', 1)}` 页 · "
            f"排序：`{SESSION_SORT_LABELS.get(sort_mode, sort_mode)}`"
        )
    elif view == PANEL_WORKSPACE:
        summary = (
            f"结果：第 `{info.get('page', 1)}` / `{info.get('total_pages', 1)}` 页 · "
            f"`{info.get('total_entries', 0)}` 个目录入口。支持继续下钻、返回和搜索。"
        )
    elif view == PANEL_COMMANDS:
        summary = f"结果：`{len(list(info.get('command_entries') or []))}` 个高频动作。这里只保留高频入口，不追求完整命令清单。"
    elif view == PANEL_STATUS:
        summary = "先看现场，再决定继续当前任务、切目录，还是切会话。"
    elements = build_status_hero(
        f"面板 · {PANEL_VIEW_LABELS.get(view, '总览')}",
        tone="info",
        summary=summary,
        facts=[
            ("当前会话", f"{current_title}\n`{session_id}`"),
            ("通道", f"`{channel}`"),
            ("目录", f"`{cwd}`"),
            ("模型", f"`{model}`"),
            ("Provider", f"`{provider}`"),
            ("Sandbox", f"`{sandbox}`"),
            ("上下文", f"`{info.get('context_usage')}`" if info.get("context_usage") else ""),
        ],
        notes=["导航和翻页优先原地更新当前消息"],
    )
    context_preview = str(info.get("context_preview") or "").strip()
    if context_preview:
        note_block = build_note_bar([f"最近上下文：{context_preview}"])
        if note_block is not None:
            elements.append(note_block)
    return elements


def _build_home_card(info: dict[str, Any]) -> dict[str, Any]:
    action_context = info.get("action_context") if isinstance(info.get("action_context"), dict) else {}
    sessions = list(info.get("sessions") or [])[:3]
    shortcuts = list(info.get("directory_shortcuts") or [])[:3]
    elements: list[dict[str, Any]] = [*_build_header_elements(info, PANEL_HOME), divider_block()]
    _append_view_nav(elements, PANEL_HOME, action_context)
    elements.append(_markdown("**进入哪一类结果**\n> 这四个入口分别收敛会话、工作区、命令和状态结果；下面的预览和结果页使用同一套项目语义。"))
    elements.append(_action_row([build_button("恢复上一条", "/resume latest", "primary", action_context), build_button("会话列表", "/resume", "default", action_context), build_button("当前状态", "/panel status", "default", action_context)]))
    elements.append(_markdown("**最近会话**\n> 想继续旧任务时，优先先看这里；如果不够，再切到完整会话结果页。"))
    _append_session_items(elements, sessions, action_context)
    elements.append(_action_row([build_button("全部会话", "/panel sessions", "default", action_context), build_button("命令式列表", "/resume", "default", action_context), build_button("帮助", "/help", "default", action_context)]))
    elements.append(_markdown("**工作区入口**\n> 先看常用目录入口；需要完整选择器时，再打开工作区结果页。"))
    _append_directory_items(elements, shortcuts, action_context)
    elements.append(_action_row([build_button("工作区选择", "/workspace", "primary", action_context), build_button("快捷目录", "/shortcut list", "default", action_context), build_button("当前状态", "/status", "default", action_context)]))
    return build_card_shell("openrelay panel", elements, tone="info")


def _build_sessions_card(info: dict[str, Any]) -> dict[str, Any]:
    action_context = info.get("action_context") if isinstance(info.get("action_context"), dict) else {}
    page = int(info.get("page") or 1)
    total_pages = int(info.get("total_pages") or 1)
    sort_mode = str(info.get("sort_mode") or "updated-desc")
    elements: list[dict[str, Any]] = [*_build_header_elements(info, PANEL_SESSIONS), divider_block()]
    _append_view_nav(elements, PANEL_SESSIONS, action_context)
    elements.append(_markdown("**会话结果**\n> 先在这里排序或翻页，再决定恢复哪条会话；真正执行仍统一走 `/resume`。"))
    elements.append(_action_row([
        build_button("最近更新", "/panel sessions --page 1 --sort updated-desc", "primary" if sort_mode == "updated-desc" else "default", action_context),
        build_button("当前优先", "/panel sessions --page 1 --sort active-first", "primary" if sort_mode == "active-first" else "default", action_context),
        build_button("恢复上一条", "/resume latest", "default", action_context),
    ]))
    page_actions = [build_button("命令式列表", f"/resume --page {page} --sort {sort_mode}", "default", action_context)]
    if page > 1:
        page_actions.insert(0, build_button("上一页", f"/panel sessions --page {page - 1} --sort {sort_mode}", "default", action_context))
    if page < total_pages:
        page_actions.append(build_button("下一页", f"/panel sessions --page {page + 1} --sort {sort_mode}", "default", action_context))
    elements.append(_action_row(page_actions))
    _append_session_items(elements, list(info.get("sessions") or []), action_context)
    return build_card_shell("openrelay panel", elements, tone="info")


def _workspace_state_text(state: str) -> str:
    if state == "current":
        return "当前目录"
    if state == "active_branch":
        return "当前目录的上级"
    return "可选目录"


def _workspace_state_border(state: str) -> str:
    if state == "current":
        return "blue"
    if state == "active_branch":
        return "indigo"
    return "grey"


def _build_workspace_search_form(action_context: dict[str, str], browser_path: str, query: str) -> dict[str, Any]:
    callback_value = {
        **action_context,
        "command": f"/workspace --path {shlex.quote(browser_path)} --page 1",
        "formFieldArgs": {"workspace_query": "--query"},
    }
    return {
        "tag": "form",
        "element_id": "workspace_search_form",
        "name": "workspace_search",
        "elements": [
            {
                "tag": "input",
                "name": "workspace_query",
                "required": False,
                "width": "fill",
                "placeholder": {"tag": "plain_text", "content": "搜索当前目录下的文件夹"},
                "default_value": query,
            },
            {
                "tag": "column_set",
                "horizontal_align": "right",
                "horizontal_spacing": "8px",
                "columns": [
                    {
                        "tag": "column",
                        "width": "auto",
                        "elements": [
                            {
                                "tag": "button",
                                "name": "workspace_search_submit",
                                "type": "primary_filled",
                                "text": {"tag": "plain_text", "content": "搜索"},
                                "behaviors": [{"type": "callback", "value": callback_value}],
                                "form_action_type": "submit",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _build_workspace_card(info: dict[str, Any]) -> dict[str, Any]:
    action_context = info.get("action_context") if isinstance(info.get("action_context"), dict) else {}
    entries = list(info.get("workspace_entries") or [])
    browser_path = str(info.get("browser_path") or "")
    parent_path = str(info.get("parent_path") or browser_path)
    query = str(info.get("query") or "")
    browser_display = str(info.get("browser_display") or "~")
    page = int(info.get("page") or 1)
    total_pages = int(info.get("total_pages") or 1)
    total_entries = int(info.get("total_entries") or len(entries))
    elements: list[dict[str, Any]] = [
        {
            "tag": "markdown",
            "content": "\n".join(
                [
                    "**工作区选择**",
                    f"> 当前目录：`{info.get('cwd', '.')}`",
                    f"> 当前浏览：`{browser_display}`",
                    "> 点目录进入下一层；点“选中当前目录”会把下一条真实消息放到这里执行。",
                ]
            ),
        },
        _build_workspace_search_form(action_context, browser_path, query),
        {
            "tag": "action",
            "actions": [
                build_button("选中当前目录", f"/workspace select {shlex.quote(browser_path)}", "primary", action_context),
                build_button("返回上一级", f"/workspace --path {shlex.quote(parent_path)} --page 1", "default", action_context),
                build_button("回到根目录", "/workspace --page 1", "default", action_context),
            ],
        },
        {
            "tag": "markdown",
            "content": f"**目录列表**\n> 第 `{page}` / `{total_pages}` 页，共 `{total_entries}` 个入口。{f' 当前搜索：`{query}`。' if query else ''}",
        },
    ]
    if not entries:
        elements.append(_markdown("> 当前目录下没有匹配的子目录。"))
    for entry in entries:
        relative_path = str(entry.get("relative_path") or "~")
        state = str(entry.get("state") or "available")
        label = str(entry.get("label") or relative_path or "目录")
        description = f"`{relative_path}` · {_workspace_state_text(state)}"
        elements.append(
            build_interactive_container(
                label,
                description,
                f"/workspace --path {shlex.quote(str(entry.get('absolute_path') or relative_path))} --page 1{f' --query {shlex.quote(query)}' if query else ''}",
                context=action_context,
                border_color=_workspace_state_border(state),
                disabled=False,
            )
        )
    page_controls = [
        build_button(
            str(page_number),
            f"/workspace --path {shlex.quote(browser_path)} --page {page_number}{f' --query {shlex.quote(query)}' if query else ''}",
            "primary" if page_number == page else "default",
            action_context,
        )
        for page_number in _page_window(page, total_pages)
    ]
    nav_controls: list[dict[str, Any]] = []
    if page > 1:
        nav_controls.append(build_button("上一页", f"/workspace --path {shlex.quote(browser_path)} --page {page - 1}{f' --query {shlex.quote(query)}' if query else ''}", "default", action_context))
    if page < total_pages:
        nav_controls.append(build_button("下一页", f"/workspace --path {shlex.quote(browser_path)} --page {page + 1}{f' --query {shlex.quote(query)}' if query else ''}", "primary", action_context))
    if query:
        nav_controls.append(build_button("清空搜索", f"/workspace --path {shlex.quote(browser_path)} --page 1", "default", action_context))
    if page_controls:
        elements.append({"tag": "action", "actions": page_controls})
    if nav_controls:
        elements.append({"tag": "action", "actions": nav_controls})
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True, "enable_forward": True, "update_multi": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "openrelay workspace"},
        },
        "body": {"elements": elements},
    }


def _build_commands_card(info: dict[str, Any]) -> dict[str, Any]:
    action_context = info.get("action_context") if isinstance(info.get("action_context"), dict) else {}
    elements: list[dict[str, Any]] = [*_build_header_elements(info, PANEL_COMMANDS), divider_block()]
    _append_view_nav(elements, PANEL_COMMANDS, action_context)
    elements.append(_markdown("**高频命令入口**\n> 这里收敛的是最常用动作，不是完整命令手册；要看完整语义，回 `/help`。"))
    _append_generic_items(elements, list(info.get("command_entries") or []), action_context)
    return build_card_shell("openrelay panel", elements, tone="info")


def _build_status_card(info: dict[str, Any]) -> dict[str, Any]:
    action_context = info.get("action_context") if isinstance(info.get("action_context"), dict) else {}
    elements: list[dict[str, Any]] = [*_build_header_elements(info, PANEL_STATUS), divider_block()]
    _append_view_nav(elements, PANEL_STATUS, action_context)
    elements.append(_markdown("**现场判断**\n> 状态页只回答“现在是什么状态、下一步去哪条主路径”，不直接承担状态变更。"))
    _append_generic_items(elements, list(info.get("status_entries") or []), action_context)
    return build_card_shell("openrelay panel", elements, tone="info")


class RuntimePanelPresenter:
    def __init__(
        self,
        config: AppConfig,
        backend_descriptors: dict[str, BackendDescriptor],
        session_browser: SessionBrowser,
        session_presentation: SessionPresentation,
        workspace: SessionWorkspaceService,
        shortcuts: SessionShortcutService,
    ) -> None:
        self.config = config
        self.backend_descriptors = backend_descriptors
        self.session_browser = session_browser
        self.session_presentation = session_presentation
        self.workspace = workspace
        self.shortcuts = shortcuts

    def build_panel_payload(
        self,
        message: IncomingMessage,
        session_key: str,
        session: SessionRecord,
        args: PanelCommandArgs,
        action_context: dict[str, str],
    ) -> tuple[dict[str, Any], str]:
        panel_info = self._build_panel_base_info(message, session_key, session, args.view, action_context)
        fallback_text = ""
        if args.view == "sessions":
            session_page = self.session_browser.list_page(session_key, session, page=args.page, sort_mode=args.sort_mode)
            card = build_panel_card(
                {
                    **panel_info,
                    "page": session_page.page,
                    "total_pages": session_page.total_pages,
                    "sort_mode": session_page.sort_mode,
                    "sessions": self.session_presentation.build_session_display_entries(session_page.entries, start_index=session_page.start_index),
                }
            )
            fallback_text = self.build_panel_sessions_text(session_page)
        elif args.view == "workspace":
            workspace_page = self.workspace.list_workspace_directories(session, browser_path=args.target_path, query=args.query, page=args.page)
            card = build_panel_card(
                {
                    **panel_info,
                    "browser_path": workspace_page.browser_path,
                    "parent_path": workspace_page.parent_path,
                    "browser_display": self.workspace.format_workspace_picker_path(workspace_page.browser_path, session),
                    "query": workspace_page.query,
                    "page": workspace_page.page,
                    "total_pages": workspace_page.total_pages,
                    "total_entries": workspace_page.total_entries,
                    "workspace_entries": [
                        {
                            "label": entry.label,
                            "relative_path": entry.relative_path,
                            "absolute_path": entry.absolute_path,
                            "state": entry.state,
                        }
                        for entry in workspace_page.entries
                    ],
                }
            )
            fallback_text = self.build_panel_workspace_text(
                workspace_page.entries,
                browser_display=self.workspace.format_workspace_picker_path(workspace_page.browser_path, session),
                page=workspace_page.page,
                total_pages=workspace_page.total_pages,
                total_entries=workspace_page.total_entries,
                query=workspace_page.query,
            )
        elif args.view == "commands":
            command_entries = self.build_panel_command_entries()
            card = build_panel_card({**panel_info, "command_entries": command_entries})
            fallback_text = self.build_panel_commands_text(command_entries)
        elif args.view == "status":
            status_entries = self.build_panel_status_entries(session)
            card = build_panel_card({**panel_info, "status_entries": status_entries})
            fallback_text = self.build_panel_status_text(status_entries)
        else:
            entries = self.session_browser.list_entries(session_key, session, limit=6)
            directory_shortcuts = self.shortcuts.build_directory_shortcut_entries(session)
            card = build_panel_card(
                {
                    **panel_info,
                    "sessions": self.session_presentation.build_session_display_entries(entries),
                    "directory_shortcuts": directory_shortcuts,
                }
            )
            fallback_text = self.build_panel_home_text(session, entries, directory_shortcuts)
        return card, fallback_text

    def build_session_list_payload(
        self,
        message: IncomingMessage,
        session_key: str,
        session: SessionRecord,
        page: int,
        sort_mode: SessionSortMode,
        action_context: dict[str, str],
    ) -> tuple[dict[str, Any], str]:
        session_page = self.session_browser.list_page(session_key, session, page=page, sort_mode=sort_mode)
        card = build_session_list_card(
            {
                "session_id": session.session_id,
                "current_title": self.session_presentation.build_session_title(session.label, session.session_id),
                "channel": format_release_channel(infer_release_channel(self.config, session)),
                "cwd": self.workspace.format_cwd(session.cwd, session),
                "page": session_page.page,
                "total_pages": session_page.total_pages,
                "total_entries": session_page.total_entries,
                "sort_mode": session_page.sort_mode,
                "has_previous": session_page.has_previous,
                "has_next": session_page.has_next,
                "action_context": action_context,
                "sessions": self.session_presentation.build_session_display_entries(session_page.entries, start_index=session_page.start_index),
            }
        )
        return card, self.session_presentation.format_session_list_page(session_page)

    def _build_panel_base_info(
        self,
        message: IncomingMessage,
        session_key: str,
        session: SessionRecord,
        view: str,
        action_context: dict[str, str],
    ) -> dict[str, Any]:
        _ = message, session_key
        return {
            "view": view,
            "session_id": session.session_id,
            "current_title": self.session_presentation.build_session_title(session.label, session.session_id),
            "channel": format_release_channel(infer_release_channel(self.config, session)),
            "cwd": self.workspace.format_cwd(session.cwd, session),
            "model": self.session_presentation.effective_model(session),
            "provider": self.backend_descriptors.get(session.backend).transport if session.backend in self.backend_descriptors else "-",
            "sandbox": session.safety_mode,
            "context_usage": self.session_presentation.format_context_usage(session),
            "context_preview": self.session_presentation.build_context_preview(session),
            "action_context": action_context,
        }

    def build_panel_command_entries(self) -> list[dict[str, str]]:
        return [
            {"title": "恢复上一条", "meta": "会话 · 最短继续路径", "preview": "直接回到最近会话，不必先打开列表。", "command": "/resume latest", "action_label": "恢复上一条", "action_type": "primary"},
            {"title": "浏览会话结果", "meta": "会话 · 翻页 / 排序", "preview": "在面板里看最近会话，再决定恢复哪一条。", "command": "/panel sessions", "action_label": "看会话"},
            {"title": "打开工作区选择器", "meta": "工作区 · 浏览 / 搜索 / 分页", "preview": "从 `~` 根别名开始浏览；默认打开配置好的工作目录，并支持搜索。", "command": "/workspace", "action_label": "选工作区"},
            {"title": "管理快捷目录", "meta": "工作区 · 新增 / 列表 / 快速切换", "preview": "用 /shortcut add|list|use 在飞书里维护自己的常用目录入口。", "command": "/shortcut list", "action_label": "看快捷目录"},
            {"title": "查看完整状态", "meta": "状态 · 目录 / 模型 / 上下文", "preview": "先确认现场，再决定继续当前任务还是切上下文。", "command": "/status", "action_label": "看状态"},
            {"title": "顶层开新对话", "meta": "隔离 · 新任务 / 切话题", "preview": "目标已经变了时，直接回顶层发新消息，不要继续堆在当前会话里。", "command": "/help", "action_label": "看说明"},
            {"title": "打开帮助", "meta": "引导 · 下一步建议", "preview": "需要 prompt 示例或命令速查时使用。", "command": "/help", "action_label": "打开帮助"},
        ]

    def build_panel_status_entries(self, session: SessionRecord) -> list[dict[str, str]]:
        channel = format_release_channel(infer_release_channel(self.config, session))
        cwd = self.workspace.format_cwd(session.cwd, session)
        context_preview = self.session_presentation.build_context_preview(session) or "还没有可总结的本地上下文。"
        return [
            {
                "title": "当前会话状态",
                "meta": f"{channel} · 目录 {cwd} · sandbox {session.safety_mode}",
                "preview": f"模型 {self.session_presentation.effective_model(session)} · 后端线程 {session.native_session_id or 'pending'}",
                "command": "/status",
                "action_label": "完整状态",
                "action_type": "primary",
            },
            {"title": "上下文与用量", "meta": f"context_usage={self.session_presentation.format_context_usage(session)}", "preview": context_preview, "command": "/usage", "action_label": "查看用量"},
            {"title": "继续当前任务", "meta": "如果目标没变，通常直接发消息最快", "preview": "要找旧会话就去会话结果；要换执行位置就去工作区选择器；不确定下一步时再打开帮助。", "command": "/help", "action_label": "打开帮助"},
        ]

    def build_panel_home_text(self, session: SessionRecord, entries: list[Any], directory_shortcuts: list[dict[str, str]]) -> str:
        lines = [
            "OpenRelay 面板",
            f"当前会话={self.session_presentation.shorten(session.label or session.session_id, 40)}",
            f"session_id={session.session_id}",
            f"channel={format_release_channel(infer_release_channel(self.config, session))}",
            f"cwd={self.workspace.format_cwd(session.cwd, session)}",
            f"model={self.session_presentation.effective_model(session)}",
            f"sandbox={session.safety_mode}",
            "",
            "结果面：/panel sessions | /panel workspace | /panel commands | /panel status",
            "提示：/panel 现在是总入口；先选会话 / 工作区 / 命令 / 状态，再进入对应结果面。",
            "工作区选择改为卡片主路径；默认打开配置好的工作目录，并支持继续下钻、返回和搜索。",
            "",
            "最近会话：",
            self.session_presentation.format_session_list(entries[:3]),
        ]
        if directory_shortcuts:
            lines.extend(["", "工作区入口："])
            lines.extend([f"- {entry['label']} -> {entry['display_path']}" for entry in directory_shortcuts[:3]])
            lines.append("面板里的快捷目录按钮会直接切到对应工作区目录。")
        else:
            lines.extend(["", "工作区入口：暂无快捷目录；可直接打开 /workspace。"])
        lines.extend([
            "",
            "commands: /panel sessions /panel workspace /panel commands /panel status /workspace /resume /resume latest /shortcut list /status /model [name|default] /sandbox [mode] /clear",
        ])
        return "\n".join(lines)

    def build_panel_sessions_text(self, session_page: Any) -> str:
        return "\n".join(["OpenRelay 面板 · 会话", self.session_presentation.format_session_list_page(session_page), "", "返回总览：/panel。"])

    def build_panel_workspace_text(self, entries: list[Any], *, browser_display: str, page: int, total_pages: int, total_entries: int, query: str) -> str:
        lines = [f"OpenRelay 面板 · 工作区 {browser_display}（第 {page}/{total_pages} 页，共 {total_entries} 个入口）", "点目录进入下一层；选中当前目录会更新当前 scope。"]
        if query:
            lines.append(f"当前搜索：{query}")
        for entry in entries:
            lines.append(f"- {entry.label} -> {entry.relative_path} [{_workspace_state_text(entry.state)}]")
        lines.extend(["", "常用动作：/workspace"])
        return "\n".join(lines)

    def build_panel_commands_text(self, command_entries: list[dict[str, str]]) -> str:
        lines = ["OpenRelay 面板 · 命令", "高频动作："]
        lines.extend([f"- {entry['title']}：{entry['preview']} ({entry['command']})" for entry in command_entries])
        return "\n".join(lines)

    def build_panel_status_text(self, status_entries: list[dict[str, str]]) -> str:
        lines = ["OpenRelay 面板 · 状态", "先看现场，再决定下一步："]
        lines.extend([f"- {entry['title']}：{entry['preview']} ({entry['command']})" for entry in status_entries])
        return "\n".join(lines)
