from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from openrelay.feishu_reply_card import (
    build_complete_card,
    build_process_panel_text as build_reply_process_panel_text,
    format_reasoning_duration,
)
from openrelay.models import SessionRecord, utc_now


LiveReplyState = dict[str, Any]
MAX_HISTORY_ITEMS = 24
EXPLORATION_COMMAND_PREFIXES = (
    "rg",
    "grep",
    "cat",
    "sed",
    "awk",
    "find",
    "fd",
    "ls",
    "tree",
    "pwd",
    "head",
    "tail",
    "wc",
    "git status",
    "git diff",
    "git show",
    "git log",
    "git branch",
    "git ls-files",
    "readlink",
    "stat",
)


def _normalize_inline(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def _history_items(state: LiveReplyState) -> list[dict[str, Any]]:
    items = state.get("history_items")
    if isinstance(items, list):
        return items
    state["history_items"] = []
    return state["history_items"]


def _append_history_item(state: LiveReplyState, item: dict[str, Any]) -> dict[str, Any]:
    items = _history_items(state)
    items.append(item)
    if len(items) > MAX_HISTORY_ITEMS:
        state["history_items"] = items[-MAX_HISTORY_ITEMS:]
    return item


def _find_history_item(state: LiveReplyState, predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any] | None:
    for item in reversed(_history_items(state)):
        if isinstance(item, dict) and predicate(item):
            return item
    return None


def _append_status_item(state: LiveReplyState, title: str, detail: str = "") -> None:
    normalized_title = _normalize_inline(title)
    normalized_detail = str(detail or "").strip()
    if not normalized_title:
        return
    last = _find_history_item(
        state,
        lambda item: item.get("type") == "status"
        and str(item.get("title") or "") == normalized_title
        and str(item.get("detail") or "") == normalized_detail,
    )
    if last is not None:
        return
    _append_history_item(
        state,
        {
            "type": "status",
            "state": "completed",
            "title": normalized_title,
            "detail": normalized_detail,
        },
    )


def _classify_command_mode(command_text: object) -> str:
    normalized = _normalize_inline(command_text).lower()
    if not normalized:
        return "command"
    for prefix in EXPLORATION_COMMAND_PREFIXES:
        if normalized == prefix or normalized.startswith(f"{prefix} "):
            return "exploration"
    return "command"


def _command_item_title(mode: object, *, completed: bool) -> str:
    if str(mode or "") == "exploration":
        return "Explored codebase" if completed else "Exploring codebase"
    return "Ran shell command" if completed else "Running shell command"


def _ensure_reasoning_item(state: LiveReplyState) -> dict[str, Any]:
    item = _find_history_item(state, lambda entry: entry.get("type") == "reasoning" and entry.get("state") == "running")
    if item is not None:
        return item
    return _append_history_item(
        state,
        {
            "type": "reasoning",
            "state": "running",
            "title": "Thinking",
            "text": "",
        },
    )


def _complete_reasoning_item(state: LiveReplyState, text: object = "") -> None:
    item = _find_history_item(state, lambda entry: entry.get("type") == "reasoning" and entry.get("state") == "running")
    if item is None:
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return
        item = _append_history_item(
            state,
            {
                "type": "reasoning",
                "state": "running",
                "title": "Thinking",
                "text": normalized_text,
            },
        )
    normalized_text = str(text or "").strip()
    if normalized_text:
        item["text"] = normalized_text
    item["state"] = "completed"
    duration_label = format_reasoning_duration(state.get("reasoning_elapsed_ms"))
    item["title"] = duration_label if duration_label and duration_label != "Thought" else "Thought"


def _resolve_command_item(state: LiveReplyState, command: dict[str, Any]) -> dict[str, Any]:
    command_id = str(command.get("id") or "").strip()
    command_text = str(command.get("command") or "").strip()
    item = _find_history_item(
        state,
        lambda entry: entry.get("type") == "command"
        and (
            (command_id and str(entry.get("command_id") or "") == command_id)
            or (not command_id and entry.get("state") == "running" and str(entry.get("command") or "") == command_text)
        ),
    )
    mode = _classify_command_mode(command_text)
    if item is None:
        item = _append_history_item(
            state,
            {
                "type": "command",
                "state": "running",
                "mode": mode,
                "title": _command_item_title(mode, completed=False),
                "command_id": command_id,
                "command": command_text,
                "exit_code": None,
                "output_preview": "",
            },
        )
    else:
        item["mode"] = mode
        item["command"] = command_text or str(item.get("command") or "")
    return item


def _complete_command_item(state: LiveReplyState, command: dict[str, Any]) -> None:
    item = _resolve_command_item(state, command)
    item["state"] = "completed"
    item["title"] = _command_item_title(item.get("mode"), completed=True)
    item["exit_code"] = command.get("exitCode") if isinstance(command.get("exitCode"), int) else item.get("exit_code")
    output_preview = str(command.get("outputPreview") or item.get("output_preview") or "").strip()
    if output_preview:
        item["output_preview"] = output_preview


def create_live_reply_state(
    session: SessionRecord,
    format_cwd: Callable[[str, SessionRecord | None, str | None], str],
) -> LiveReplyState:
    return {
        "session_id": session.session_id,
        "native_session_id": session.native_session_id,
        "cwd": format_cwd(session.cwd, session),
        "history": [],
        "history_items": [],
        "heading": "正在启动 Codex",
        "status": "等待响应",
        "current_command": "",
        "last_command": None,
        "commands": [],
        "last_reasoning": "",
        "reasoning_text": "",
        "reasoning_started_at": "",
        "reasoning_elapsed_ms": 0,
        "partial_text": "",
        "spinner_frame": 0,
        "started_at": utc_now(),
    }


def push_live_history(state: LiveReplyState, text: object) -> None:
    value = " ".join(str(text or "").split()).strip()
    if not value:
        return
    history = state.setdefault("history", [])
    if history and history[-1] == value:
        return
    history.append(value)
    state["history"] = history[-12:]


def finalize_reasoning_timing(state: LiveReplyState) -> None:
    if int(state.get("reasoning_elapsed_ms") or 0) > 0:
        return
    raw_started_at = str(state.get("reasoning_started_at") or "").strip()
    if not raw_started_at:
        return
    try:
        started_at = datetime.fromisoformat(raw_started_at)
        elapsed_ms = max(0, int((datetime.fromisoformat(utc_now()) - started_at).total_seconds() * 1000))
    except Exception:
        return
    if elapsed_ms > 0:
        state["reasoning_elapsed_ms"] = elapsed_ms


def build_process_panel_text(state: LiveReplyState | dict[str, Any] | None) -> str:
    return build_reply_process_panel_text(state if isinstance(state, dict) else None)


def apply_live_progress(state: LiveReplyState, event: dict[str, Any] | None) -> None:
    if not event:
        return
    event_type = event.get("type")
    if event_type == "run.started":
        state["heading"] = "正在启动 Codex"
        state["status"] = "正在准备回复"
        _append_status_item(state, "Starting Codex", "Preparing reply")
        push_live_history(state, state["status"])
        return
    if event_type == "thread.started":
        state["native_session_id"] = str(event.get("threadId") or state.get("native_session_id") or "")
        state["heading"] = "原生会话已连接"
        state["status"] = "正在准备回复"
        _append_status_item(state, "Connected session", f"`{state['native_session_id']}`" if state["native_session_id"] else "")
        push_live_history(state, "原生会话已连接")
        push_live_history(state, state["status"])
        return
    if event_type == "assistant.partial":
        finalize_reasoning_timing(state)
        _complete_reasoning_item(state)
        state["heading"] = "正在生成回复"
        state["status"] = "正在输出内容"
        if isinstance(event.get("text"), str):
            state["partial_text"] = event["text"]
        push_live_history(state, state["status"])
        return
    if event_type == "reasoning.started":
        state["heading"] = "正在分析"
        state["status"] = "整理上下文与计划"
        state["reasoning_started_at"] = utc_now()
        state["reasoning_elapsed_ms"] = 0
        _ensure_reasoning_item(state)
        push_live_history(state, state["status"])
        return
    if event_type == "reasoning.delta":
        state["heading"] = "正在分析"
        state["status"] = "整理上下文与计划"
        if not str(state.get("reasoning_started_at") or "").strip():
            state["reasoning_started_at"] = utc_now()
        if isinstance(event.get("text"), str):
            state["reasoning_text"] = event["text"]
            state["last_reasoning"] = event["text"]
            _ensure_reasoning_item(state)["text"] = event["text"].strip()
        push_live_history(state, state["status"])
        return
    if event_type == "command.started":
        command = event.get("command") if isinstance(event.get("command"), dict) else {}
        finalize_reasoning_timing(state)
        _complete_reasoning_item(state)
        state["heading"] = "正在执行命令"
        state["status"] = f"执行 {command.get('command')}" if command.get("command") else "正在执行命令"
        state["current_command"] = str(command.get("command") or "")
        _resolve_command_item(state, command)
        push_live_history(state, state["status"])
        return
    if event_type == "command.completed":
        command = event.get("command") if isinstance(event.get("command"), dict) else {}
        state["heading"] = "正在整理结果"
        state["status"] = f"完成 {command.get('command')}" if command.get("command") else "命令已完成"
        state["current_command"] = ""
        state["last_command"] = command or None
        commands = state.setdefault("commands", [])
        if isinstance(commands, list) and command:
            commands.append(command)
            state["commands"] = commands[-8:]
        _complete_command_item(state, command)
        push_live_history(state, state["status"])
        return
    if event_type == "reasoning.completed":
        state["heading"] = "正在分析"
        state["status"] = "整理上下文与计划"
        if isinstance(event.get("text"), str):
            state["last_reasoning"] = event["text"]
            state["reasoning_text"] = event["text"]
        finalize_reasoning_timing(state)
        _complete_reasoning_item(state, event.get("text"))
        push_live_history(state, state["status"])
        return
    if event_type == "agent.message":
        finalize_reasoning_timing(state)
        _complete_reasoning_item(state)
        state["heading"] = "正在整理回复"
        if isinstance(event.get("text"), str) and event["text"].strip():
            state["status"] = event["text"]
        push_live_history(state, state["status"])
        return
    if event_type == "turn.completed":
        finalize_reasoning_timing(state)
        _complete_reasoning_item(state)
        state["heading"] = "即将完成"
        state["status"] = "正在收尾输出"
        push_live_history(state, state["status"])


def build_reply_card(
    text: str,
    title: str = "openrelay",
    *,
    process_text: str = "",
) -> dict[str, object]:
    return build_complete_card(
        text,
        panel_text=process_text,
        panel_title="🧾 中间过程",
    )
