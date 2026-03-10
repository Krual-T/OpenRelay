from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from openrelay.config import AppConfig
from openrelay.models import SessionRecord
from openrelay.release import format_release_channel, get_release_workspace, get_session_workspace_root, infer_release_channel
from openrelay.session_browser import SessionListEntry, SessionListPage, SESSION_SORT_UPDATED
from openrelay.state import StateStore


class SessionUX:
    def __init__(self, config: AppConfig, store: StateStore):
        self.config = config
        self.store = store

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
        if release_channel:
            workspace_root = get_release_workspace(self.config, release_channel).resolve()
        elif session is not None:
            workspace_root = get_session_workspace_root(self.config, session).resolve()
        else:
            workspace_root = self.config.workspace_root.resolve()
        absolute = Path(cwd).expanduser().resolve() if cwd else workspace_root
        try:
            relative = absolute.relative_to(workspace_root)
        except ValueError:
            return str(absolute)
        return "." if str(relative) == "." else str(relative)

    def resolve_cwd(self, current_cwd: str, relative_path: str, session: SessionRecord) -> Path:
        workspace_root = get_session_workspace_root(self.config, session).resolve()
        base = Path(current_cwd).expanduser().resolve() if current_cwd else workspace_root
        requested = Path(relative_path.strip()).expanduser()
        target = requested.resolve() if requested.is_absolute() else (base / requested).resolve()
        if target != workspace_root and workspace_root not in target.parents:
            raise ValueError("path escapes workspace root")
        if not target.exists():
            raise ValueError(f"path does not exist: {relative_path}")
        if not target.is_dir():
            raise ValueError(f"not a directory: {relative_path}")
        return target

    def build_directory_shortcut_entries(self, session: SessionRecord, limit: int = 4) -> list[dict[str, str]]:
        channel = infer_release_channel(self.config, session)
        workspace_root = get_session_workspace_root(self.config, session).resolve()
        entries: list[dict[str, str]] = []
        for shortcut in self.list_directory_shortcuts():
            if "all" not in shortcut.channels and channel not in shortcut.channels:
                continue
            target = self._resolve_directory_shortcut_target(shortcut.path, workspace_root)
            if target is None:
                continue
            entries.append(
                {
                    "label": shortcut.name,
                    "display_path": self.format_cwd(str(target), None, channel),
                    "command": f"/cwd {shlex.quote(str(target))}",
                    "channels": ",".join(shortcut.channels),
                    "raw_path": shortcut.path,
                }
            )
            if len(entries) >= limit:
                break
        return entries

    def list_directory_shortcuts(self) -> tuple[DirectoryShortcut, ...]:
        merged: list[DirectoryShortcut] = []
        seen: set[str] = set()
        for shortcut in (*self.store.list_directory_shortcuts(), *self.config.directory_shortcuts):
            name_key = shortcut.name.strip().lower()
            if not name_key or name_key in seen:
                continue
            seen.add(name_key)
            merged.append(shortcut)
        return tuple(merged)

    def resolve_directory_shortcut(self, name: str, session: SessionRecord) -> Path | None:
        requested_name = name.strip().lower()
        if not requested_name:
            return None
        channel = infer_release_channel(self.config, session)
        workspace_root = get_session_workspace_root(self.config, session).resolve()
        for shortcut in self.list_directory_shortcuts():
            if shortcut.name.strip().lower() != requested_name:
                continue
            if "all" not in shortcut.channels and channel not in shortcut.channels:
                return None
            return self._resolve_directory_shortcut_target(shortcut.path, workspace_root)
        return None

    def _resolve_directory_shortcut_target(self, raw_path: str, workspace_root: Path) -> Path | None:
        requested = Path(str(raw_path or "").strip()).expanduser()
        if not requested:
            return None
        target = requested.resolve() if requested.is_absolute() else (workspace_root / requested).resolve()
        if target != workspace_root and workspace_root not in target.parents:
            return None
        if not target.exists() or not target.is_dir():
            return None
        return target

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
            parts.append(f"目录 {self.format_cwd(entry.cwd, None, entry.release_channel or 'main')}")
        if entry.message_count:
            parts.append(f"{entry.message_count} 条消息")
        if entry.native_session_id and entry.native_session_id != entry.session_id:
            parts.append(f"native={entry.native_session_id}")
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
        if not entries:
            return "没有可恢复的历史会话。"
        blocks: list[str] = []
        for display in self.build_session_display_entries(entries):
            lines = [f"{display['index']}. {'[当前] ' if display.get('active') else ''}{display['title']}"]
            identifier = f"id={display['resume_token']}"
            native_id = str(display.get("native_session_id") or "")
            if native_id and native_id != display["session_id"]:
                identifier += f" · native={native_id}"
            lines.append(f"   {identifier}")
            if display.get("meta"):
                lines.append(f"   {display['meta']}")
            if display.get("preview"):
                lines.append(f"   预览：{display['preview']}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

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
                identifier += f" · native={native_id}"
            lines.append(f"   {identifier}")
            if display.get("meta"):
                lines.append(f"   {display['meta']}")
            if display.get("preview"):
                lines.append(f"   预览：{display['preview']}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def format_resume_success(self, session: SessionRecord, *, imported: bool = False, entry: SessionListEntry | None = None) -> str:
        lines = [
            f"已恢复会话：{self.build_session_title(session.label, session.session_id)}{'（来自原生 Codex 历史）' if imported else ''}",
            f"session_id={session.session_id}",
            f"cwd={self.format_cwd(session.cwd, session)}",
        ]
        if entry and entry.native_session_id and entry.native_session_id != session.session_id:
            lines.append(f"native_session_id={entry.native_session_id}")
        history = self.store.list_messages(session.session_id)[-4:]
        if history:
            lines.extend(["", "最近历史："])
            for item in history:
                role = "用户" if item.get("role") == "user" else "助手"
                lines.append(f"- {role}：{self.shorten(item.get('content', ''), 96)}")
        elif entry and (entry.first_user_message or self.build_session_preview(entry)):
            lines.extend(["", f"首条问题：{entry.first_user_message or self.build_session_preview(entry)}"])
        lines.extend(["", "继续发送消息即可；想在指定目录进入 Codex：先 /cwd <path>，再发消息。"])
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
                return [f"- 原生会话：{session.native_session_id}", "- 本地还没有缓存到更多上下文消息。"]
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

    def build_panel_text(self, session: SessionRecord) -> str:
        lines = [
            "OpenRelay 面板",
            f"当前会话={self.shorten(session.label or session.session_id, 40)}",
            f"session_id={session.session_id}",
            f"channel={format_release_channel(infer_release_channel(self.config, session))}",
            f"cwd={self.format_cwd(session.cwd, session)}",
            f"model={self.effective_model(session)}",
            f"sandbox={session.safety_mode}",
            "结果面：/panel sessions | /panel directories | /panel commands | /panel status",
            "提示：/panel 现在是总入口；先选会话 / 目录 / 命令 / 状态，再进入对应结果面。",
            "目录入口仍复用 /cwd 主路径；如需强制切回稳定版本，发送 /main 原因。",
        ]
        shortcut_entries = self.build_directory_shortcut_entries(session)
        if shortcut_entries:
            lines.append("常用目录：")
            lines.extend([f"- {entry['label']} -> {entry['display_path']}" for entry in shortcut_entries])
            lines.append("面板里的快捷目录按钮会直接执行稳定的 /cwd 切换。")
        lines.append("commands: /panel sessions /panel directories /panel commands /panel status /resume list /resume latest /cwd <path> /main /develop /new /status /model [name|default] /sandbox [mode] /clear")
        return "\n".join(lines)
