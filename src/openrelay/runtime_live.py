from __future__ import annotations

from typing import Any, Callable

from openrelay.card_theme import build_card_shell, infer_final_tone
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
        state["session_id"] = state["native_session_id"] or state.get("session_id", "")
        state["heading"] = "原生会话已连接"
        state["status"] = "正在准备回复"
        push_live_history(state, "原生会话已连接")
        push_live_history(state, state["status"])
        return
    if event_type == "assistant.partial":
        state["heading"] = "正在生成回复"
        state["status"] = "正在输出内容"
        if isinstance(event.get("text"), str):
            state["partial_text"] = event["text"]
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
        push_live_history(state, state["status"])
        return
    if event_type == "agent.message":
        state["heading"] = "正在整理回复"
        if isinstance(event.get("text"), str) and event["text"].strip():
            state["status"] = event["text"]
        push_live_history(state, state["status"])
        return
    if event_type == "turn.completed":
        state["heading"] = "即将完成"
        state["status"] = "正在收尾输出"
        push_live_history(state, state["status"])



def build_reply_card(text: str, title: str = "openrelay") -> dict[str, object]:
    content = text.strip() or "回复为空。"
    return build_card_shell(
        title,
        [{"tag": "div", "text": {"tag": "lark_md", "content": content}}],
        tone=infer_final_tone(content),
    )
