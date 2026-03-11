from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from openrelay.feishu_reply_card import build_complete_card, build_process_panel_text as build_reply_process_panel_text
from openrelay.models import SessionRecord, utc_now


LiveReplyState = dict[str, Any]


def create_live_reply_state(
    session: SessionRecord,
    format_cwd: Callable[[str, SessionRecord | None, str | None], str],
) -> LiveReplyState:
    return {
        "session_id": session.session_id,
        "native_session_id": session.native_session_id,
        "cwd": format_cwd(session.cwd, session),
        "history": [],
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
        push_live_history(state, state["status"])
        return
    if event_type == "thread.started":
        state["native_session_id"] = str(event.get("threadId") or state.get("native_session_id") or "")
        state["heading"] = "原生会话已连接"
        state["status"] = "正在准备回复"
        push_live_history(state, "原生会话已连接")
        push_live_history(state, state["status"])
        return
    if event_type == "assistant.partial":
        finalize_reasoning_timing(state)
        state["heading"] = "正在生成回复"
        state["status"] = "正在输出内容"
        if isinstance(event.get("text"), str):
            state["partial_text"] = event["text"]
        push_live_history(state, state["status"])
        return
    if event_type == "reasoning.started":
        state["heading"] = "正在分析"
        state["status"] = "整理上下文与计划"
        if not str(state.get("reasoning_started_at") or "").strip():
            state["reasoning_started_at"] = utc_now()
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
        push_live_history(state, state["status"])
        return
    if event_type == "command.started":
        command = event.get("command") if isinstance(event.get("command"), dict) else {}
        state["heading"] = "正在执行命令"
        state["status"] = f"执行 {command.get('command')}" if command.get("command") else "正在执行命令"
        state["current_command"] = str(command.get("command") or "")
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
        push_live_history(state, state["status"])
        return
    if event_type == "reasoning.completed":
        state["heading"] = "正在分析"
        state["status"] = "整理上下文与计划"
        if isinstance(event.get("text"), str):
            state["last_reasoning"] = event["text"]
            state["reasoning_text"] = event["text"]
        finalize_reasoning_timing(state)
        push_live_history(state, state["status"])
        return
    if event_type == "agent.message":
        finalize_reasoning_timing(state)
        state["heading"] = "正在整理回复"
        if isinstance(event.get("text"), str) and event["text"].strip():
            state["status"] = event["text"]
        push_live_history(state, state["status"])
        return
    if event_type == "turn.completed":
        finalize_reasoning_timing(state)
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
