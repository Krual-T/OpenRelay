from __future__ import annotations

import json
import logging
from typing import Any, Callable

from openrelay.agent_runtime import ApprovalDecision, ApprovalRequest, LiveTurnViewModel, ToolState
from openrelay.core import SessionRecord, utc_now
from openrelay.feishu import build_complete_card, render_transcript_markdown

LOGGER = logging.getLogger("openrelay.presentation.live_turn")


class LiveTurnPresenter:
    def create_initial_snapshot(
        self,
        session: SessionRecord,
        format_cwd: Callable[[str, SessionRecord | None, str | None], str],
    ) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "native_session_id": session.native_session_id,
            "cwd": format_cwd(session.cwd, session),
            "history": [],
            "history_items": [],
            "plan_history_items": [],
            "transcript_items": [],
            "heading": "Generating reply",
            "status": "Waiting for streamed output",
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

    def build_snapshot(
        self,
        state: LiveTurnViewModel,
        *,
        previous: dict[str, Any] | None = None,
        session: SessionRecord | None = None,
        format_cwd: Callable[[str, SessionRecord | None, str | None], str] | None = None,
    ) -> dict[str, Any]:
        previous = previous or {}
        heading, status = self.build_status_heading(state)
        snapshot = {
            "session_id": state.session_id,
            "native_session_id": state.native_session_id,
            "cwd": format_cwd(session.cwd, session) if (session is not None and format_cwd is not None) else str(previous.get("cwd") or ""),
            "history": list(previous.get("history") or []),
            "history_items": self._history_items(state, previous),
            "plan_history_items": [],
            "transcript_items": [],
            "heading": heading,
            "status": status,
            "current_command": self._current_command(state),
            "last_command": previous.get("last_command"),
            "commands": [],
            "last_reasoning": state.reasoning_text,
            "reasoning_text": state.reasoning_text,
            "reasoning_started_at": previous.get("reasoning_started_at") or "",
            "reasoning_elapsed_ms": previous.get("reasoning_elapsed_ms") or 0,
            "partial_text": state.assistant_text,
            "spinner_frame": int(previous.get("spinner_frame") or 0),
            "started_at": previous.get("started_at") or utc_now(),
            "committed_partial_text": previous.get("committed_partial_text") or "",
        }
        if state.reasoning_text and not snapshot["reasoning_started_at"]:
            snapshot["reasoning_started_at"] = previous.get("started_at") or utc_now()
        snapshot["transcript_items"] = self._merge_transcript_items(snapshot["history_items"], previous)
        snapshot["plan_history_items"] = [
            dict(item)
            for item in snapshot["transcript_items"]
            if isinstance(item, dict) and item.get("type") == "plan"
        ]
        if snapshot["plan_history_items"]:
            LOGGER.info(
                "live turn snapshot built session_id=%s turn_id=%s plan_steps=%s transcript_plan_details=%s",
                state.session_id,
                state.turn_id,
                [
                    {"step": step.step, "status": step.status}
                    for step in state.plan_steps
                ],
                [str(item.get("detail") or "") for item in snapshot["plan_history_items"]],
            )
        return snapshot

    def build_process_text(self, state: dict[str, Any] | LiveTurnViewModel) -> str:
        return self.build_transcript_markdown(state)

    def build_transcript_markdown(
        self,
        state: dict[str, Any] | LiveTurnViewModel,
        *,
        include_summary: bool = True,
    ) -> str:
        snapshot = state if isinstance(state, dict) else self.build_snapshot(state)
        return render_transcript_markdown(snapshot, include_summary=include_summary)

    def build_final_reply(self, state: LiveTurnViewModel) -> str:
        return state.assistant_text

    def build_status_heading(self, state: LiveTurnViewModel) -> tuple[str, str]:
        if state.pending_approval is not None:
            return ("Waiting for approval", state.pending_approval.title or "Waiting for user input")
        if state.status == "completed":
            return ("Finishing up", "Wrapping up output")
        if state.status == "failed":
            return ("Run failed", state.error_message or "The run failed")
        if state.status == "interrupted":
            return ("Interrupted", state.error_message or "The run was interrupted")
        if state.tools:
            active_tool = self._active_tool(state)
            if active_tool is not None:
                return self._tool_status(active_tool)
        if state.reasoning_text:
            return ("Thinking", "Working through the task")
        if state.assistant_text:
            return ("Generating reply", "Streaming output")
        return ("Generating reply", "Waiting for streamed output")

    def build_reply_card(self, text: str, *, process_text: str = "") -> dict[str, object]:
        transcript_markdown = str(process_text or "").strip()
        return build_complete_card(text, transcript_markdown=transcript_markdown)

    def build_streaming_card(self, state: dict[str, Any] | LiveTurnViewModel) -> dict[str, object]:
        snapshot = state if isinstance(state, dict) else self.build_snapshot(state)
        return build_complete_card(
            snapshot.get("partial_text") or "",
            transcript_markdown=self.build_transcript_markdown(snapshot),
        )

    def build_final_card(self, state: dict[str, Any] | LiveTurnViewModel, *, fallback_text: str = "") -> dict[str, object]:
        snapshot = state if isinstance(state, dict) else self.build_snapshot(state)
        text = str(snapshot.get("partial_text") or fallback_text or "").strip() or "回复为空。"
        process_text = self.build_transcript_markdown(snapshot, include_summary=False)
        return build_complete_card(text, panel_text=process_text)

    def build_approval_resolved_snapshot(
        self,
        previous: dict[str, Any],
        request: ApprovalRequest,
        decision: ApprovalDecision,
    ) -> dict[str, Any]:
        snapshot = dict(previous)
        history_items = [dict(item) for item in list(previous.get("history_items") or []) if isinstance(item, dict)]
        updated = False
        for item in history_items:
            if item.get("type") != "interaction":
                continue
            if str(item.get("interaction_id") or "") != request.approval_id:
                continue
            item["state"] = "completed" if decision.decision in {"accept", "accept_for_session", "custom"} else "cancelled"
            item["detail"] = self._approval_resolution_label(decision)
            updated = True
            break
        if not updated:
            history_items.append(
                {
                    "type": "interaction",
                    "state": "completed" if decision.decision in {"accept", "accept_for_session", "custom"} else "cancelled",
                    "interaction_id": request.approval_id,
                    "title": request.title,
                    "detail": self._approval_resolution_label(decision),
                }
            )
        snapshot["history_items"] = history_items
        snapshot["heading"] = "Resuming"
        snapshot["status"] = self._approval_resolution_label(decision)
        return snapshot

    def with_native_session_id(self, previous: dict[str, Any], native_session_id: str) -> dict[str, Any]:
        snapshot = dict(previous)
        snapshot["native_session_id"] = str(native_session_id or "")
        return snapshot

    def bump_spinner(self, previous: dict[str, Any]) -> dict[str, Any]:
        snapshot = dict(previous)
        snapshot["spinner_frame"] = (int(previous.get("spinner_frame", 0) or 0) + 1) % 3
        return snapshot

    def _history_items(self, state: LiveTurnViewModel, previous: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if state.reasoning_text:
            items.append(
                {
                    "type": "reasoning",
                    "state": "running" if state.status == "running" else "completed",
                    "title": "Thinking" if state.status == "running" else "Thought",
                    "text": state.reasoning_text,
                }
            )
        for tool in state.tools:
            item = self._tool_history_item(tool, state)
            if item is not None:
                items.append(item)
        if state.plan_steps:
            plan_steps = [
                {"step": step.step.strip(), "status": step.status}
                for step in state.plan_steps
                if step.step.strip()
            ]
            plan_lines = [f"{entry['status']} {entry['step']}" for entry in plan_steps]
            if plan_lines:
                items.append(
                    {
                        "type": "plan",
                        "state": "running" if state.status == "running" else "completed",
                        "title": "Plan",
                        "steps": plan_steps,
                        "detail": "\n".join(plan_lines),
                    }
                )
        items.extend(self._system_history_items(state))
        for backend_event in state.backend_events:
            items.append(
                {
                    "type": "backend_event",
                    "state": "completed" if backend_event.level != "error" else "error",
                    "title": backend_event.title or "Unexpected backend event",
                    "detail": self._format_backend_event_detail(backend_event.detail, backend_event.raw_payload),
                }
            )
        if state.pending_approval is not None:
            items.append(
                {
                    "type": "interaction",
                    "state": "running",
                    "interaction_id": state.pending_approval.approval_id,
                    "title": state.pending_approval.title,
                    "detail": state.pending_approval.description,
                }
            )
        return self._merge_preserved_interactions(items, previous)

    def _merge_preserved_interactions(
        self,
        items: list[dict[str, Any]],
        previous: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        if previous is None:
            return items
        existing_ids = {
            str(item.get("interaction_id") or "")
            for item in items
            if item.get("type") == "interaction" and str(item.get("interaction_id") or "")
        }
        preserved: list[dict[str, Any]] = []
        for item in list(previous.get("history_items") or []):
            if not isinstance(item, dict) or item.get("type") != "interaction":
                continue
            interaction_id = str(item.get("interaction_id") or "")
            if interaction_id and interaction_id in existing_ids:
                continue
            if str(item.get("state") or "").strip() == "running":
                continue
            preserved.append(dict(item))
        return preserved + items

    def _merge_transcript_items(
        self,
        items: list[dict[str, Any]],
        previous: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        prior_items = (previous or {}).get("transcript_items")
        if not isinstance(prior_items, list):
            prior_items = (previous or {}).get("history_items")
        transcript_items = [dict(item) for item in list(prior_items or []) if isinstance(item, dict)]
        keyed_indexes = {
            key: index
            for index, item in enumerate(transcript_items)
            if (key := self._transcript_item_key(item)) is not None
        }
        for item in items:
            current_item = dict(item)
            if current_item.get("type") == "plan":
                signature = self._plan_signature(current_item)
                current_item["transcript_signature"] = signature
                last_plan_index = next(
                    (
                        index
                        for index in range(len(transcript_items) - 1, -1, -1)
                        if transcript_items[index].get("type") == "plan"
                    ),
                    None,
                )
                if last_plan_index is not None and str(transcript_items[last_plan_index].get("transcript_signature") or "") == signature:
                    transcript_items[last_plan_index] = current_item
                    continue
                transcript_items.append(current_item)
                continue
            key = self._transcript_item_key(current_item)
            if key is None:
                transcript_items.append(current_item)
                continue
            existing_index = keyed_indexes.get(key)
            if existing_index is None:
                keyed_indexes[key] = len(transcript_items)
                transcript_items.append(current_item)
                continue
            transcript_items[existing_index] = current_item
        return transcript_items

    def _plan_signature(self, item: dict[str, Any]) -> str:
        steps = item.get("steps")
        if not isinstance(steps, list):
            return str(item.get("detail") or "").strip()
        normalized_steps = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            normalized_steps.append(
                {
                    "step": str(step.get("step") or "").strip(),
                    "status": str(step.get("status") or "").strip(),
                }
            )
        return json.dumps(normalized_steps, ensure_ascii=False, sort_keys=True)

    def _transcript_item_key(self, item: dict[str, Any]) -> tuple[str, str] | None:
        item_type = str(item.get("type") or "").strip()
        if not item_type or item_type == "plan":
            return None
        if item_type == "command":
            return (item_type, str(item.get("command_id") or "").strip())
        if item_type == "web_search":
            return (item_type, str(item.get("search_id") or "").strip())
        if item_type == "file_change":
            return (item_type, str(item.get("file_change_id") or "").strip())
        if item_type == "collab":
            return (item_type, str(item.get("collab_id") or "").strip())
        if item_type == "interaction":
            return (item_type, str(item.get("interaction_id") or "").strip())
        if item_type == "reasoning":
            return (item_type, "current")
        detail = str(item.get("detail") or "").strip()
        title = str(item.get("title") or "").strip()
        if not title and not detail:
            return None
        return (item_type, json.dumps({"title": title, "detail": detail}, ensure_ascii=False, sort_keys=True))

    def _format_backend_event_detail(self, detail: str, raw_payload: dict[str, Any]) -> str:
        blocks: list[str] = []
        normalized_detail = str(detail or "").strip()
        if normalized_detail:
            blocks.append(normalized_detail)
        raw_event = raw_payload.get("raw_event")
        if isinstance(raw_event, dict) and raw_event:
            blocks.append(json.dumps(raw_event, ensure_ascii=False, indent=2, sort_keys=True))
        return "\n\n".join(blocks).strip()

    def _system_history_items(self, state: LiveTurnViewModel) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        _ = state
        return items

    def _terminal_interaction_detail(self, process_id: str, stdin: str) -> str:
        parts: list[str] = []
        if process_id:
            parts.append(f"process: {process_id}")
        normalized_stdin = str(stdin or "")
        if normalized_stdin:
            parts.append(f"stdin: {normalized_stdin}")
        return "\n".join(parts).strip() or "terminal interaction"

    def _tool_history_item(
        self,
        tool: ToolState,
        state: LiveTurnViewModel,
    ) -> dict[str, Any] | None:
        if tool.kind == "command":
            return {
                "type": "command",
                "state": "running" if tool.status == "running" else "completed",
                "mode": self._command_mode(tool.preview or tool.title),
                "title": "Running shell command" if tool.status == "running" else "Ran shell command",
                "command_id": tool.tool_id,
                "command": tool.preview or tool.title,
                "exit_code": tool.exit_code,
                "output_preview": tool.detail,
            }
        if tool.kind == "web_search":
            return {
                "type": "web_search",
                "state": "running" if tool.status == "running" else "completed",
                "title": "Searching web" if tool.status == "running" else "Searched web",
                "search_id": tool.tool_id,
                "query": tool.preview,
                "queries": [tool.preview] if tool.preview else [],
            }
        if tool.kind == "file_change":
            detail = tool.detail or state.latest_diff
            return {
                "type": "file_change",
                "state": "running" if tool.status == "running" else "completed",
                "title": "Updating files" if tool.status == "running" else "Updated files",
                "file_change_id": tool.tool_id,
                "changes": tool.provider_payload.get("changes") if isinstance(tool.provider_payload.get("changes"), list) else [],
                "detail": detail,
            }
        if tool.kind == "custom":
            return {
                "type": "collab",
                "state": "running" if tool.status == "running" else "completed",
                "title": tool.title or "Updating agent",
                "collab_id": tool.tool_id,
                "tool": tool.title,
                "prompt": tool.preview,
                "receiver_thread_ids": list(tool.provider_payload.get("receiverThreadIds") or []),
                "agents": tool.provider_payload.get("agentsStates") if isinstance(tool.provider_payload.get("agentsStates"), dict) else {},
            }
        return None

    def _active_tool(self, state: LiveTurnViewModel) -> ToolState | None:
        for tool in reversed(state.tools):
            if tool.status == "running":
                return tool
        return None

    def _tool_status(self, tool: ToolState) -> tuple[str, str]:
        if tool.kind == "command":
            return ("Running shell command", tool.preview or tool.title or "Executing command")
        if tool.kind == "web_search":
            return ("Searching web", tool.preview or "Running web search")
        if tool.kind == "file_change":
            return ("Updating files", tool.preview or "Applying file changes")
        return (tool.title or "Running tool", tool.preview or tool.title or "Running tool")

    def _current_command(self, state: LiveTurnViewModel) -> str:
        active_tool = self._active_tool(state)
        if active_tool is None or active_tool.kind != "command":
            return ""
        return active_tool.preview or active_tool.title

    def _command_mode(self, command_text: str) -> str:
        normalized = " ".join(str(command_text or "").split()).strip().lower()
        if not normalized:
            return "command"
        for prefix in ("rg", "grep", "cat", "sed", "find", "fd", "ls", "tree", "pwd", "git status", "git diff", "git show", "git log"):
            if normalized == prefix or normalized.startswith(f"{prefix} "):
                return "exploration"
        return "command"

    def _approval_resolution_label(self, decision: ApprovalDecision) -> str:
        if decision.decision == "accept":
            return "Approval accepted"
        if decision.decision == "accept_for_session":
            return "Approved for session"
        if decision.decision == "decline":
            return "Approval declined"
        if decision.decision == "cancel":
            return "Approval cancelled"
        return "Approval resolved"
