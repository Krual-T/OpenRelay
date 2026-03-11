from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from openrelay.card_theme import build_card_shell, build_collapsible_panel, build_note_bar, infer_final_tone, status_badge
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


def format_reasoning_duration(reasoning_elapsed_ms: object) -> str:
    try:
        total_seconds = max(0, int(int(reasoning_elapsed_ms or 0) / 1000))
    except Exception:
        return "Thought"
    if total_seconds <= 0:
        return "Thought"
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes, seconds = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


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
    reasoning_text: str = "",
    reasoning_elapsed_ms: int | None = None,
) -> dict[str, object]:
    content = text.strip() or "回复为空。"
    tone = infer_final_tone(content)
    elements: list[dict[str, Any]] = []
    status_note = build_note_bar([status_badge(tone), "继续追问时直接回复当前线程即可"])
    if status_note is not None:
        elements.append(status_note)
    reasoning_panel = build_collapsible_panel(
        f"💭 {format_reasoning_duration(reasoning_elapsed_ms)}",
        reasoning_text,
        expanded=False,
    )
    if reasoning_panel is not None:
        elements.append(reasoning_panel)
    elements.append({"tag": "markdown", "content": content})
    follow_up_note = build_note_bar(["如果目标没变，不用先发命令，直接补充任务 / 报错 / 文件路径。"])
    if follow_up_note is not None:
        elements.append(follow_up_note)
    return build_card_shell(title, elements, tone=tone)
