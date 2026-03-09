from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from openrelay.config import AppConfig
from openrelay.models import SessionRecord, SessionSummary
from openrelay.native_sessions import find_native_session, import_native_session, list_native_sessions
from openrelay.release import format_release_channel, get_release_workspace, get_session_workspace_root, infer_release_channel
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
        absolute = Path(cwd).resolve() if cwd else workspace_root
        try:
            relative = absolute.relative_to(workspace_root)
        except ValueError:
            return str(absolute)
        return "." if str(relative) == "." else str(relative)

    def resolve_cwd(self, current_cwd: str, relative_path: str, session: SessionRecord) -> Path:
        workspace_root = get_session_workspace_root(self.config, session).resolve()
        base = Path(current_cwd).resolve() if current_cwd else workspace_root
        target = (base / relative_path).resolve()
        if target != workspace_root and workspace_root not in target.parents:
            raise ValueError("path escapes workspace root")
        return target

    def build_session_title(self, entry: dict[str, object]) -> str:
        return self.shorten(str(entry.get("label") or entry.get("first_user_message") or entry.get("session_id") or "未命名会话"), 40) or "未命名会话"

    def build_session_preview(self, entry: dict[str, object]) -> str:
        preview = self.shorten(str(entry.get("last_assistant_message") or entry.get("first_user_message") or ""), 84)
        label = str(entry.get("label") or "")
        return "" if preview == label else preview

    def build_session_meta(self, entry: dict[str, object]) -> str:
        parts: list[str] = []
        if entry.get("active"):
            parts.append("当前")
        elif entry.get("origin") == "native":
            parts.append("原生" if entry.get("matches_workspace") else "原生·外部目录")
        else:
            parts.append("本地")
        parts.append(format_release_channel(str(entry.get("release_channel") or "main")))
        updated_at = str(entry.get("updated_at") or "")
        if updated_at:
            parts.append(updated_at[:16].replace("T", " "))
        cwd = str(entry.get("cwd") or "")
        if cwd:
            parts.append(f"目录 {self.format_cwd(cwd, None, str(entry.get('release_channel') or 'main'))}")
        message_count = int(entry.get("message_count") or 0)
        if message_count:
            parts.append(f"{message_count} 条消息")
        return " · ".join(parts)

    def build_merged_session_list(self, session_key: str, session: SessionRecord, limit: int = 12) -> list[dict[str, object]]:
        local_sessions = self.store.list_sessions(session_key, limit=limit)
        merged: list[dict[str, object]] = []
        seen: set[str] = set()
        for entry in local_sessions:
            key = entry.native_session_id or entry.session_id
            seen.add(key)
            merged.append(
                {
                    "session_id": key,
                    "native_session_id": entry.native_session_id or "",
                    "label": entry.label,
                    "updated_at": entry.updated_at,
                    "active": entry.active,
                    "origin": "local",
                    "release_channel": entry.release_channel,
                    "cwd": entry.cwd,
                    "first_user_message": entry.first_user_message,
                    "last_assistant_message": entry.last_assistant_message,
                    "message_count": entry.message_count,
                    "matches_workspace": True,
                }
            )
        for entry in self.list_importable_native_sessions(local_sessions, session, limit):
            if entry.session_id in seen:
                continue
            seen.add(entry.session_id)
            merged.append(
                {
                    "session_id": entry.session_id,
                    "native_session_id": entry.session_id,
                    "label": entry.label,
                    "updated_at": entry.updated_at,
                    "active": False,
                    "origin": "native",
                    "release_channel": infer_release_channel(self.config, session),
                    "cwd": entry.cwd,
                    "first_user_message": entry.first_user_message,
                    "last_assistant_message": "",
                    "message_count": 0,
                    "matches_workspace": entry.matches_workspace,
                }
            )
        merged.sort(key=lambda item: (not bool(item.get("active")), str(item.get("updated_at") or "")))
        merged = merged[:limit]
        entries: list[dict[str, object]] = []
        for index, entry in enumerate(merged, start=1):
            payload = {**entry, "index": index}
            payload["title"] = self.build_session_title(payload)
            payload["preview"] = self.build_session_preview(payload)
            payload["meta"] = self.build_session_meta(payload)
            entries.append(payload)
        return entries

    def list_importable_native_sessions(self, local_sessions: list[SessionSummary], session: SessionRecord, limit: int = 10):
        if session.backend != "codex":
            return []
        known_ids = {entry.native_session_id or entry.session_id for entry in local_sessions}
        return [entry for entry in list_native_sessions(self.config, limit=limit) if entry.session_id not in known_ids]

    def resume_local_or_native(self, session_key: str, session: SessionRecord, target: str, merged_sessions: list[dict[str, object]]):
        normalized = target.strip()
        resolved_target = normalized
        if normalized.isdigit():
            index = int(normalized) - 1
            if 0 <= index < len(merged_sessions):
                resolved_target = str(merged_sessions[index].get("session_id") or normalized)
        resumed = self.store.resume_session(session_key, resolved_target)
        if resumed is not None:
            entry = next((item for item in merged_sessions if item.get("session_id") == resumed.session_id or item.get("native_session_id") == resumed.session_id or item.get("session_id") == resolved_target), None)
            return resumed, False, entry
        if not resolved_target or resolved_target.lower() in {"latest", "prev", "previous"}:
            latest_native = self.list_importable_native_sessions(self.store.list_sessions(session_key, limit=20), session, 1)
            if not latest_native:
                return None, False, None
            imported = import_native_session(self.store, session_key, latest_native[0], session)
            entry = next((item for item in merged_sessions if item.get("session_id") == latest_native[0].session_id), None)
            return imported, True, entry
        native = find_native_session(self.config, resolved_target)
        if native is None:
            return None, False, None
        imported = import_native_session(self.store, session_key, native, session)
        entry = next((item for item in merged_sessions if item.get("session_id") == native.session_id), None)
        return imported, True, entry

    def format_merged_session_list(self, entries: list[dict[str, object]]) -> str:
        if not entries:
            return "没有可恢复的历史会话。"
        blocks: list[str] = []
        for entry in entries:
            lines = [f"{entry['index']}. {'[当前] ' if entry.get('active') else ''}{entry['title']}"]
            lines.append(f"   id={entry['session_id']}")
            if entry.get("meta"):
                lines.append(f"   {entry['meta']}")
            if entry.get("preview"):
                lines.append(f"   预览：{entry['preview']}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def format_resume_success(self, session: SessionRecord, imported: bool = False, entry: dict[str, object] | None = None) -> str:
        lines = [
            f"已恢复会话：{self.build_session_title({'label': session.label, 'session_id': session.session_id})}{'（来自原生 Codex 历史）' if imported else ''}",
            f"session_id={session.session_id}",
            f"cwd={self.format_cwd(session.cwd, session)}",
        ]
        history = self.store.list_messages(session.session_id)[-4:]
        if history:
            lines.extend(["", "最近历史："])
            for item in history:
                role = "用户" if item.get("role") == "user" else "助手"
                lines.append(f"- {role}：{self.shorten(item.get('content', ''), 96)}")
        elif entry and (entry.get("first_user_message") or entry.get("preview")):
            lines.extend(["", f"首条问题：{entry.get('first_user_message') or entry.get('preview')}"])
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
        return "\n".join([
            "OpenRelay 面板",
            f"当前会话={self.shorten(session.label or session.session_id, 40)}",
            f"session_id={session.session_id}",
            f"channel={format_release_channel(infer_release_channel(self.config, session))}",
            f"cwd={self.format_cwd(session.cwd, session)}",
            f"model={self.effective_model(session)}",
            f"sandbox={session.safety_mode}",
            "提示：先 /cwd <path> 再发消息，就会在目标目录进入 Codex；如需强制切回稳定版本，发送 /main 原因。",
            "commands: /restart /main /stable /develop /new /resume /resume latest /cwd <path> /cd <path> /status /model [name|default] /sandbox [mode] /clear",
        ])
