from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from openrelay.feishu import (
    build_complete_card,
    build_process_panel_text as build_reply_process_panel_text,
    format_reasoning_duration,
)
from openrelay.core import SessionRecord, utc_now


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


def _find_summary_item(state: LiveReplyState) -> dict[str, Any] | None:
    return _find_history_item(state, lambda entry: entry.get("type") == "summary" and entry.get("state") == "running")


def _complete_summary_item(state: LiveReplyState) -> None:
    item = _find_summary_item(state)
    if item is None:
        return
    item["state"] = "completed"
    partial_text = str(state.get("partial_text") or "")
    if partial_text:
        state["committed_partial_text"] = partial_text


def _summary_segment_text(state: LiveReplyState, full_text: object) -> str:
    current_text = str(full_text or "")
    committed_text = str(state.get("committed_partial_text") or "")
    if committed_text and current_text.startswith(committed_text):
        return current_text[len(committed_text) :].strip()
    return current_text.strip()


def _update_summary_item(state: LiveReplyState, full_text: object) -> None:
    current_text = str(full_text or "").strip()
    if not current_text:
        return
    segment_text = _summary_segment_text(state, current_text)
    if not segment_text:
        return
    item = _find_summary_item(state)
    if item is None:
        item = _append_history_item(
            state,
            {
                "type": "summary",
                "state": "running",
                "text": segment_text,
            },
        )
    else:
        item["text"] = segment_text
    state["partial_text"] = current_text


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


def _normalize_search_query(search: dict[str, Any]) -> str:
    query = _normalize_inline(search.get("query"))
    if query:
        return query
    action = search.get("action") if isinstance(search.get("action"), dict) else {}
    action_query = _normalize_inline(action.get("query"))
    if action_query:
        return action_query
    queries = action.get("queries")
    if isinstance(queries, list):
        for entry in queries:
            normalized = _normalize_inline(entry)
            if normalized:
                return normalized
    return ""


def _search_queries(search: dict[str, Any]) -> list[str]:
    values: list[str] = []
    primary = _normalize_search_query(search)
    if primary:
        values.append(primary)
    action = search.get("action") if isinstance(search.get("action"), dict) else {}
    queries = action.get("queries")
    if isinstance(queries, list):
        for entry in queries:
            normalized = _normalize_inline(entry)
            if normalized and normalized not in values:
                values.append(normalized)
    return values


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


def _file_change_kind(change: dict[str, Any]) -> str:
    kind = change.get("kind")
    if not isinstance(kind, dict):
        return ""
    return str(kind.get("type") or "").strip()


def _summarize_file_change_title(changes: list[dict[str, Any]], *, completed: bool) -> str:
    kinds = {_file_change_kind(change) for change in changes if isinstance(change, dict)}
    kinds.discard("")
    if kinds == {"add"}:
        return "Added" if completed else "Adding"
    if kinds == {"update"}:
        return "Edited" if completed else "Editing"
    if kinds == {"delete"}:
        return "Deleted" if completed else "Deleting"
    return "Updated files" if completed else "Updating files"


def _resolve_file_change_item(state: LiveReplyState, file_change: dict[str, Any]) -> dict[str, Any]:
    change_id = str(file_change.get("id") or "").strip()
    item = _find_history_item(
        state,
        lambda entry: entry.get("type") == "file_change"
        and ((change_id and str(entry.get("file_change_id") or "") == change_id) or (not change_id and entry.get("state") == "running")),
    )
    changes = [change for change in (file_change.get("changes") or []) if isinstance(change, dict)]
    title = _summarize_file_change_title(changes, completed=False)
    if item is None:
        item = _append_history_item(
            state,
            {
                "type": "file_change",
                "state": "running",
                "title": title,
                "file_change_id": change_id,
                "changes": changes,
            },
        )
    else:
        item["title"] = title
        item["changes"] = changes or list(item.get("changes") or [])
    return item


def _complete_file_change_item(state: LiveReplyState, file_change: dict[str, Any]) -> None:
    item = _resolve_file_change_item(state, file_change)
    changes = [change for change in (file_change.get("changes") or []) if isinstance(change, dict)]
    item["state"] = str(file_change.get("status") or "completed").strip() or "completed"
    item["title"] = _summarize_file_change_title(changes or list(item.get("changes") or []), completed=True)
    if changes:
        item["changes"] = changes


def _collab_tool_title(tool: object, *, completed: bool) -> str:
    normalized = str(tool or "").strip()
    if normalized == "spawnAgent":
        return "Spawned" if completed else "Spawning"
    if normalized == "sendInput":
        return "Sent input to" if completed else "Sending input to"
    if normalized == "resumeAgent":
        return "Resumed" if completed else "Resuming"
    if normalized == "wait":
        return "Finished waiting for" if completed else "Waiting for"
    if normalized == "closeAgent":
        return "Closed" if completed else "Closing"
    return "Updated agent" if completed else "Updating agent"


def _collab_tool_state(status: object) -> str:
    normalized = str(status or "").strip()
    if normalized == "inProgress":
        return "running"
    if normalized == "failed":
        return "failed"
    return "completed"


def _resolve_collab_item(state: LiveReplyState, collab: dict[str, Any]) -> dict[str, Any]:
    collab_id = str(collab.get("id") or "").strip()
    item = _find_history_item(
        state,
        lambda entry: entry.get("type") == "collab"
        and ((collab_id and str(entry.get("collab_id") or "") == collab_id) or (not collab_id and entry.get("state") == "running")),
    )
    tool = str(collab.get("tool") or "").strip()
    if item is None:
        item = _append_history_item(
            state,
            {
                "type": "collab",
                "state": _collab_tool_state(collab.get("status")),
                "title": _collab_tool_title(tool, completed=False),
                "collab_id": collab_id,
                "tool": tool,
                "agents": collab.get("agentsStates") if isinstance(collab.get("agentsStates"), dict) else {},
                "receiver_thread_ids": list(collab.get("receiverThreadIds") or []),
                "prompt": str(collab.get("prompt") or "").strip(),
            },
        )
    else:
        item["tool"] = tool or str(item.get("tool") or "")
        item["agents"] = collab.get("agentsStates") if isinstance(collab.get("agentsStates"), dict) else item.get("agents", {})
        item["receiver_thread_ids"] = list(collab.get("receiverThreadIds") or item.get("receiver_thread_ids") or [])
        prompt = str(collab.get("prompt") or "").strip()
        if prompt:
            item["prompt"] = prompt
    return item


def _complete_collab_item(state: LiveReplyState, collab: dict[str, Any]) -> None:
    item = _resolve_collab_item(state, collab)
    item["state"] = _collab_tool_state(collab.get("status"))
    item["title"] = _collab_tool_title(item.get("tool"), completed=item["state"] != "running")


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


def _resolve_web_search_item(state: LiveReplyState, search: dict[str, Any]) -> dict[str, Any]:
    search_id = str(search.get("id") or "").strip()
    item = _find_history_item(
        state,
        lambda entry: entry.get("type") == "web_search"
        and ((search_id and str(entry.get("search_id") or "") == search_id) or (not search_id and entry.get("state") == "running")),
    )
    queries = _search_queries(search)
    if item is None:
        item = _append_history_item(
            state,
            {
                "type": "web_search",
                "state": "running",
                "title": "Searching web",
                "search_id": search_id,
                "query": queries[0] if queries else "",
                "queries": queries,
            },
        )
    else:
        item["query"] = queries[0] if queries else str(item.get("query") or "")
        item["queries"] = queries or list(item.get("queries") or [])
    return item


def _complete_web_search_item(state: LiveReplyState, search: dict[str, Any]) -> None:
    item = _resolve_web_search_item(state, search)
    item["state"] = "completed"
    item["title"] = "Searched web"


def _resolve_plan_item(state: LiveReplyState, plan_id: str) -> dict[str, Any]:
    item = _find_history_item(
        state,
        lambda entry: entry.get("type") == "plan" and str(entry.get("plan_id") or "") == plan_id,
    )
    if item is not None:
        return item
    return _append_history_item(
        state,
        {
            "type": "plan",
            "state": "running",
            "title": "Updating plan",
            "plan_id": plan_id,
            "detail": "",
        },
    )


def _resolve_interaction_item(state: LiveReplyState, interaction: dict[str, Any]) -> dict[str, Any]:
    interaction_id = str(interaction.get("id") or "").strip()
    item = _find_history_item(
        state,
        lambda entry: entry.get("type") == "interaction"
        and ((interaction_id and str(entry.get("interaction_id") or "") == interaction_id) or (not interaction_id and entry.get("state") == "running")),
    )
    title = _normalize_inline(interaction.get("title")) or "Waiting for input"
    detail = str(interaction.get("detail") or "").strip()
    if item is None:
        item = _append_history_item(
            state,
            {
                "type": "interaction",
                "state": "running",
                "title": title,
                "interaction_id": interaction_id,
                "detail": detail,
            },
        )
    else:
        item["title"] = title
        if detail:
            item["detail"] = detail
    return item


def _complete_interaction_item(state: LiveReplyState, interaction: dict[str, Any]) -> None:
    item = _resolve_interaction_item(state, interaction)
    raw_state = str(interaction.get("state") or "completed").strip()
    item["state"] = raw_state or "completed"
    detail = str(interaction.get("detail") or "").strip()
    if detail:
        item["detail"] = detail


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
        "heading": "Starting Codex",
        "status": "Waiting for response",
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
    if event_type != "assistant.partial":
        _complete_summary_item(state)
    if event_type == "run.started":
        state["heading"] = "Starting Codex"
        state["status"] = "Preparing reply"
        _append_status_item(state, "Starting Codex", "Preparing reply")
        push_live_history(state, state["status"])
        return
    if event_type == "thread.started":
        state["native_session_id"] = str(event.get("threadId") or state.get("native_session_id") or "")
        state["heading"] = "Connected native session"
        state["status"] = "Preparing reply"
        _append_status_item(state, "Connected session", f"`{state['native_session_id']}`" if state["native_session_id"] else "")
        push_live_history(state, "Connected native session")
        push_live_history(state, state["status"])
        return
    if event_type == "assistant.partial":
        finalize_reasoning_timing(state)
        _complete_reasoning_item(state)
        state["heading"] = "Generating reply"
        state["status"] = "Streaming output"
        if isinstance(event.get("text"), str):
            _update_summary_item(state, event["text"])
        push_live_history(state, state["status"])
        return
    if event_type == "reasoning.started":
        state["heading"] = "Analyzing"
        state["status"] = "Planning next step"
        state["reasoning_started_at"] = utc_now()
        state["reasoning_elapsed_ms"] = 0
        _ensure_reasoning_item(state)
        push_live_history(state, state["status"])
        return
    if event_type == "reasoning.delta":
        state["heading"] = "Analyzing"
        state["status"] = "Planning next step"
        if not str(state.get("reasoning_started_at") or "").strip():
            state["reasoning_started_at"] = utc_now()
        if isinstance(event.get("text"), str):
            state["reasoning_text"] = event["text"]
            state["last_reasoning"] = event["text"]
            _ensure_reasoning_item(state)["text"] = event["text"].strip()
        push_live_history(state, state["status"])
        return
    if event_type == "web_search.started":
        search = event.get("search") if isinstance(event.get("search"), dict) else {}
        finalize_reasoning_timing(state)
        _complete_reasoning_item(state)
        state["heading"] = "Searching web"
        query = _normalize_search_query(search)
        state["status"] = f"Search {query}" if query else "Searching the web"
        _resolve_web_search_item(state, search)
        push_live_history(state, state["status"])
        return
    if event_type == "web_search.completed":
        search = event.get("search") if isinstance(event.get("search"), dict) else {}
        state["heading"] = "Reviewing search results"
        query = _normalize_search_query(search)
        state["status"] = f"Searched {query}" if query else "Search completed"
        _complete_web_search_item(state, search)
        push_live_history(state, state["status"])
        return
    if event_type == "command.started":
        command = event.get("command") if isinstance(event.get("command"), dict) else {}
        finalize_reasoning_timing(state)
        _complete_reasoning_item(state)
        state["heading"] = "Running command"
        state["status"] = f"Run {command.get('command')}" if command.get("command") else "Running command"
        state["current_command"] = str(command.get("command") or "")
        _resolve_command_item(state, command)
        push_live_history(state, state["status"])
        return
    if event_type == "command.completed":
        command = event.get("command") if isinstance(event.get("command"), dict) else {}
        state["heading"] = "Summarizing result"
        state["status"] = f"Completed {command.get('command')}" if command.get("command") else "Command completed"
        state["current_command"] = ""
        state["last_command"] = command or None
        commands = state.setdefault("commands", [])
        if isinstance(commands, list) and command:
            commands.append(command)
            state["commands"] = commands[-8:]
        _complete_command_item(state, command)
        push_live_history(state, state["status"])
        return
    if event_type == "file_change.started":
        file_change = event.get("file_change") if isinstance(event.get("file_change"), dict) else {}
        finalize_reasoning_timing(state)
        _complete_reasoning_item(state)
        state["heading"] = "Updating files"
        state["status"] = _summarize_file_change_title(
            [change for change in (file_change.get("changes") or []) if isinstance(change, dict)],
            completed=False,
        )
        _resolve_file_change_item(state, file_change)
        push_live_history(state, state["status"])
        return
    if event_type == "file_change.completed":
        file_change = event.get("file_change") if isinstance(event.get("file_change"), dict) else {}
        state["heading"] = "Updated files"
        state["status"] = _summarize_file_change_title(
            [change for change in (file_change.get("changes") or []) if isinstance(change, dict)],
            completed=True,
        )
        _complete_file_change_item(state, file_change)
        push_live_history(state, state["status"])
        return
    if event_type == "collab.started":
        collab = event.get("collab") if isinstance(event.get("collab"), dict) else {}
        finalize_reasoning_timing(state)
        _complete_reasoning_item(state)
        state["heading"] = "Coordinating agents"
        state["status"] = _collab_tool_title(collab.get("tool"), completed=False)
        _resolve_collab_item(state, collab)
        push_live_history(state, state["status"])
        return
    if event_type == "collab.completed":
        collab = event.get("collab") if isinstance(event.get("collab"), dict) else {}
        state["heading"] = "Coordinating agents"
        state["status"] = _collab_tool_title(collab.get("tool"), completed=_collab_tool_state(collab.get("status")) != "running")
        _complete_collab_item(state, collab)
        push_live_history(state, state["status"])
        return
    if event_type == "reasoning.completed":
        state["heading"] = "Analyzing"
        state["status"] = "Planning next step"
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
        state["heading"] = "Drafting response"
        if isinstance(event.get("text"), str) and event["text"].strip():
            state["status"] = event["text"]
        push_live_history(state, state["status"])
        return
    if event_type == "plan.delta":
        state["heading"] = "Planning"
        state["status"] = "Updating plan"
        item = _resolve_plan_item(state, "plan-stream")
        if isinstance(event.get("text"), str):
            item["detail"] = event["text"]
        push_live_history(state, state["status"])
        return
    if event_type == "plan.updated":
        state["heading"] = "Planning"
        state["status"] = "Plan updated"
        explanation = str(event.get("explanation") or "").strip()
        plan = event.get("plan") if isinstance(event.get("plan"), list) else []
        item = _resolve_plan_item(state, "plan-stream")
        item["state"] = "completed"
        item["title"] = "Updated plan"
        detail_lines = [explanation] if explanation else []
        for step in plan:
            if not isinstance(step, dict):
                continue
            step_text = _normalize_inline(step.get("step"))
            step_status = _normalize_inline(step.get("status"))
            if step_text:
                detail_lines.append(f"{step_status or 'pending'}: {step_text}")
        item["detail"] = "\n".join(detail_lines).strip()
        push_live_history(state, state["status"])
        return
    if event_type == "interaction.requested":
        interaction = event.get("interaction") if isinstance(event.get("interaction"), dict) else {}
        finalize_reasoning_timing(state)
        _complete_reasoning_item(state)
        state["heading"] = "Waiting for input"
        state["status"] = _normalize_inline(interaction.get("title")) or "Waiting for user input"
        _resolve_interaction_item(state, interaction)
        push_live_history(state, state["status"])
        return
    if event_type == "interaction.resolved":
        interaction = event.get("interaction") if isinstance(event.get("interaction"), dict) else {}
        state["heading"] = "Resuming"
        state["status"] = _normalize_inline(interaction.get("detail")) or "User input received"
        _complete_interaction_item(state, interaction)
        push_live_history(state, state["status"])
        return
    if event_type == "turn.completed":
        finalize_reasoning_timing(state)
        _complete_reasoning_item(state)
        state["heading"] = "Finishing up"
        state["status"] = "Wrapping up output"
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
        panel_title="Execution Log",
    )
