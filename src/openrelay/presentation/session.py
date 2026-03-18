from __future__ import annotations

from typing import Any

from openrelay.core import AppConfig, SessionRecord, format_release_channel, infer_release_channel
from openrelay.feishu.cards import build_button, build_card_shell, build_note_bar, build_section_block, build_status_hero, divider_block, markdown_block
from openrelay.storage import StateStore

from openrelay.session.browser import SESSION_SORT_ACTIVE, SESSION_SORT_UPDATED, SessionListEntry, SessionListPage
from openrelay.session.workspace import SessionWorkspaceService


def build_resume_list_command(target: str = "", *, page: int = 1, sort_mode: str = SESSION_SORT_UPDATED) -> str:
    parts = ["/resume"]
    if target:
        parts.append(target)
    parts.extend(["--page", str(max(page, 1)), "--sort", sort_mode])
    return " ".join(parts)


def build_resume_card_command(*, page: int = 1) -> str:
    if page <= 1:
        return "/resume"
    return f"/resume --page {max(page, 1)}"


def _page_window(page: int, known_page_count: int, width: int = 5) -> list[int]:
    if known_page_count <= 0:
        return []
    current = max(page, 1)
    size = max(width, 1)
    start = max(1, current - (size // 2))
    end = min(known_page_count, start + size - 1)
    start = max(1, end - size + 1)
    return list(range(start, end + 1))


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
    current_session_id = str(info.get("current_session_id") or info.get("session_id") or "-")

    sort_label = "最近更新优先" if sort_mode == SESSION_SORT_UPDATED else "当前会话优先"
    next_sort = SESSION_SORT_ACTIVE if sort_mode == SESSION_SORT_UPDATED else SESSION_SORT_UPDATED
    next_sort_label = "切到当前优先" if sort_mode == SESSION_SORT_UPDATED else "切到最近更新"

    elements: list[dict[str, Any]] = [
        *build_status_hero(
            "会话列表",
            tone="info",
            summary="先选排序和页码，再决定恢复哪条会话；分页与排序会优先原地更新当前卡片。",
            facts=[
                ("当前会话", f"{current_title}\n`{current_session_id}`"),
                ("排序", f"`{sort_label}`"),
                ("页码", f"第 `{page}` 页"),
            ],
            notes=["点击按钮即可恢复；也可以直接手输 `/resume <编号|session_id|latest>`"],
        ),
        divider_block(),
    ]

    if sessions:
        for entry in sessions:
            elements.append(build_section_block("会话条目", [_session_text(entry)], emoji="🗂️"))
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
        elements.append(build_section_block("会话条目", ["> 当前没有可恢复的会话。"], emoji="🗂️"))

    controls = [build_button(next_sort_label, build_resume_list_command(page=1, sort_mode=next_sort), "default", action_context)]
    if has_previous:
        controls.insert(0, build_button("上一页", build_resume_list_command(page=page - 1, sort_mode=sort_mode), "default", action_context))
    if has_next:
        controls.append(build_button("下一页", build_resume_list_command(page=page + 1, sort_mode=sort_mode), "primary", action_context))
    footer_note = build_note_bar(["排序切换不会改变恢复语义；真正执行仍统一走 `/resume` 主路径。"])
    if footer_note is not None:
        elements.append(footer_note)
    elements.append({"tag": "action", "actions": controls})
    elements.append({"tag": "action", "actions": [build_button("恢复上一条", build_resume_list_command("latest", page=page, sort_mode=sort_mode), "default", action_context), build_button("面板", "/panel", "default", action_context), build_button("帮助", "/help", "default", action_context)]})

    return build_card_shell("openrelay sessions", elements, tone="info")


def build_backend_session_list_card(info: dict[str, Any]) -> dict[str, Any]:
    sessions = list(info.get("sessions") or [])
    action_context = info.get("action_context") if isinstance(info.get("action_context"), dict) else {}
    page = int(info.get("page") or 1)
    known_page_count = int(info.get("known_page_count") or page)
    has_previous = bool(info.get("has_previous"))
    has_next = bool(info.get("has_next"))
    backend_name = str(info.get("backend_name") or "runtime").strip() or "runtime"
    elements: list[dict[str, Any]] = []

    if sessions:
        for entry in sessions:
            title = str(entry.get("title") or entry.get("label") or entry.get("session_id") or "未命名会话")
            lines = [f"**{entry.get('index', '-')}. {title}**{' · 当前' if entry.get('active') else ''}"]
            meta = str(entry.get("meta") or "").strip()
            if meta:
                lines.append(meta)
            session_id = str(entry.get("session_id") or entry.get("resume_token") or "").strip()
            if session_id:
                lines.append(f"`{session_id}`")
            elements.append(markdown_block("\n".join(lines)))
            elements.append(
                {
                    "tag": "action",
                    "actions": [
                        build_button(
                            "连接此会话",
                            f"/resume {str(entry.get('session_id') or entry.get('resume_token') or '').strip()}",
                            "primary" if entry.get("active") else "default",
                            action_context,
                        )
                    ],
                }
            )
    else:
        elements.append(markdown_block("> 当前没有可连接的后端会话。"))

    page_controls: list[dict[str, Any]] = []
    for page_number in _page_window(page, max(known_page_count, page)):
        page_controls.append(
            build_button(
                str(page_number),
                build_resume_card_command(page=page_number),
                "primary" if page_number == page else "default",
                action_context,
            )
        )
    nav_controls: list[dict[str, Any]] = []
    if has_previous:
        nav_controls.append(build_button("上一页", build_resume_card_command(page=page - 1), "default", action_context))
    if has_next:
        nav_controls.append(build_button("下一页", build_resume_card_command(page=page + 1), "primary", action_context))
    if page_controls or nav_controls:
        elements.append(divider_block())
    if page_controls:
        elements.append({"tag": "action", "actions": page_controls})
    if nav_controls:
        elements.append({"tag": "action", "actions": nav_controls})
    return build_card_shell(f"Relay {backend_name} thread histories", elements, tone="info")


class SessionPresentation:
    def __init__(self, config: AppConfig, store: StateStore):
        self.config = config
        self.store = store
        self.workspace = SessionWorkspaceService(config)

    def shorten(self, text: str, length: int) -> str:
        value = " ".join((text or "").split())
        if len(value) <= length:
            return value
        return f"{value[:length - 3]}..."

    def effective_model(self, session: SessionRecord) -> str:
        return session.model_override or self.config.backend.default_model or "codex"

    def label_session_if_needed(self, session: SessionRecord, first_prompt: str) -> SessionRecord:
        if session.label:
            return session
        return SessionRecord(
            session_id=session.session_id,
            base_key=session.base_key,
            backend=session.backend,
            cwd=session.cwd,
            label=self.shorten(first_prompt, 40),
            model_override=session.model_override,
            safety_mode=session.safety_mode,
            native_session_id=session.native_session_id,
            release_channel=session.release_channel,
            created_at=session.created_at,
        )

    def format_cwd(self, cwd: str, session: SessionRecord | None = None, release_channel: str | None = None) -> str:
        return self.workspace.format_cwd(cwd, session, release_channel)

    def build_session_title(self, label: str, session_id: str, first_user_message: str = "") -> str:
        return self.shorten(label or first_user_message or session_id or "未命名会话", 40) or "未命名会话"

    def build_session_preview(self, entry: SessionListEntry) -> str:
        preview = self.shorten(entry.last_assistant_message or entry.first_user_message or "", 84)
        return "" if preview == entry.label else preview

    def build_session_meta(self, entry: SessionListEntry) -> str:
        parts: list[str] = []
        if entry.active:
            parts.append("当前")
        elif entry.origin == "native":
            parts.append("原生" if entry.matches_workspace else "原生·外部目录")
        else:
            parts.append("本地")
        parts.append(format_release_channel(entry.release_channel or "main"))
        if entry.updated_at:
            parts.append(entry.updated_at[:16].replace("T", " "))
        if entry.cwd:
            parts.append(f"目录 {self.workspace.format_cwd(entry.cwd, None, entry.release_channel or 'main')}")
        if entry.message_count:
            parts.append(f"{entry.message_count} 条消息")
        if entry.native_session_id and entry.native_session_id != entry.session_id:
            parts.append(f"thread={entry.native_session_id}")
        return " · ".join(parts)

    def build_session_display_entries(self, entries: list[SessionListEntry], start_index: int = 1) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for index, entry in enumerate(entries, start=start_index):
            payloads.append(
                {
                    "index": index,
                    "session_id": entry.session_id,
                    "resume_token": entry.resume_token,
                    "native_session_id": entry.native_session_id,
                    "active": entry.active,
                    "title": self.build_session_title(entry.label, entry.session_id, entry.first_user_message),
                    "preview": self.build_session_preview(entry),
                    "meta": self.build_session_meta(entry),
                }
            )
        return payloads

    def format_session_list(self, entries: list[SessionListEntry]) -> str:
        return self._format_session_displays(self.build_session_display_entries(entries))

    def format_session_list_page(self, session_page: SessionListPage) -> str:
        sort_label = "最近更新优先" if session_page.sort_mode == SESSION_SORT_UPDATED else "当前会话优先"
        header = [
            f"最近会话（第 {session_page.page} 页，排序：{sort_label}）：",
            self._format_session_displays(self.build_session_display_entries(session_page.entries, start_index=session_page.start_index)),
            "",
            "使用 /resume <编号|session_id|latest> 恢复。翻页与排序卡片动作会保留当前上下文。",
        ]
        return "\n".join(line for line in header if line)

    def _format_session_displays(self, displays: list[dict[str, Any]]) -> str:
        if not displays:
            return "没有可恢复的历史会话。"
        blocks: list[str] = []
        for display in displays:
            lines = [f"{display['index']}. {'[当前] ' if display.get('active') else ''}{display['title']}"]
            identifier = f"id={display['resume_token']}"
            native_id = str(display.get("native_session_id") or "")
            if native_id and native_id != display["session_id"]:
                identifier += f" · thread={native_id}"
            lines.append(f"   {identifier}")
            if display.get("meta"):
                lines.append(f"   {display['meta']}")
            if display.get("preview"):
                lines.append(f"   预览：{display['preview']}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def format_resume_success(self, session: SessionRecord, *, entry: SessionListEntry | None = None) -> str:
        lines = [
            f"已恢复会话：{self.build_session_title(session.label, session.session_id)}",
            f"session_id={session.session_id}",
            f"cwd={self.workspace.format_cwd(session.cwd, session)}",
        ]
        if entry and entry.native_session_id and entry.native_session_id != session.session_id:
            lines.append(f"backend_thread={entry.native_session_id}")
        history = self.store.list_messages(session.session_id)[-4:]
        if history:
            lines.extend(["", "最近历史："])
            for item in history:
                role = "用户" if item.get("role") == "user" else "助手"
                lines.append(f"- {role}：{self.shorten(item.get('content', ''), 96)}")
        elif entry and (entry.first_user_message or self.build_session_preview(entry)):
            lines.extend(["", f"首条问题：{entry.first_user_message or self.build_session_preview(entry)}"])
        lines.extend(["", "继续发送消息即可；想在指定目录进入 Codex：先打开 /workspace 选目录，再发消息。"])
        return "\n".join(lines)

    def build_context_preview(self, session: SessionRecord, limit: int = 2) -> str:
        messages = self.store.list_messages(session.session_id)[-limit:]
        if not messages:
            return ""
        parts: list[str] = []
        for item in messages:
            role = "用户" if item.get("role") == "user" else "助手"
            parts.append(f"{role}：{self.shorten(item.get('content', ''), 48)}")
        return " | ".join(parts)

    def build_context_lines(self, session: SessionRecord, limit: int = 4) -> list[str]:
        messages = self.store.list_messages(session.session_id)[-limit:]
        if not messages:
            if session.native_session_id:
                return [f"- 后端线程：{session.native_session_id}", "- 本地还没有缓存到更多上下文消息。"]
            return ["- 当前还没有上下文消息。发出第一条真实消息后，这里会显示最近上下文。"]
        lines: list[str] = []
        for item in messages:
            role = "用户" if item.get("role") == "user" else "助手"
            lines.append(f"- {role}：{self.shorten(item.get('content', ''), 96)}")
        return lines

    def format_context_usage(self, session: SessionRecord) -> str:
        usage = session.last_usage if isinstance(session.last_usage, dict) else {}
        total_tokens = usage.get("total_tokens")
        model_context_window = usage.get("model_context_window")
        try:
            total_value = int(total_tokens)
            window_value = int(model_context_window)
        except (TypeError, ValueError):
            return "unknown"
        if window_value <= 0:
            return "unknown"
        percent = total_value / window_value * 100
        return f"{percent:.1f}% ({total_value}/{window_value})"

    def build_usage_lines(self, session: SessionRecord) -> list[str]:
        usage = session.last_usage if isinstance(session.last_usage, dict) else {}
        context_usage = self.format_context_usage(session)
        lines = [f"context_usage={context_usage}"]
        if usage:
            parts: list[str] = []
            if usage.get("input_tokens") is not None:
                parts.append(f"in={usage['input_tokens']}")
            if usage.get("cached_input_tokens") is not None:
                parts.append(f"cache={usage['cached_input_tokens']}")
            if usage.get("output_tokens") is not None:
                parts.append(f"out={usage['output_tokens']}")
            if usage.get("total_tokens") is not None:
                parts.append(f"total={usage['total_tokens']}")
            if usage.get("model_context_window") is not None:
                parts.append(f"window={usage['model_context_window']}")
            if parts:
                lines.append("usage_detail=" + " ".join(parts))
        else:
            lines.append("usage_detail=unavailable")
        return lines
