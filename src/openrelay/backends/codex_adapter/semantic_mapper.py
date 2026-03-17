from __future__ import annotations

from typing import Any

from openrelay.agent_runtime import PlanStep, ToolState, UsageSnapshot

from .event_registry import CodexEventDescriptor
from .semantic_events import CodexRawEventEnvelope, CodexSemanticEvent


def combine_indexed_text(parts_by_index: dict[int, str]) -> str:
    parts: list[str] = []
    for index in sorted(parts_by_index):
        text = str(parts_by_index.get(index) or "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()


def _normalize_event_item_type(item_type: object) -> str:
    normalized = str(item_type or "").strip()
    if not normalized:
        return ""
    return normalized[:1].lower() + normalized[1:]


def _normalize_event_item(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized["type"] = _normalize_event_item_type(item.get("type"))
    if "summary_text" in normalized and "summary" not in normalized:
        normalized["summary"] = normalized.get("summary_text")
    if "raw_content" in normalized and "content" not in normalized:
        normalized["content"] = normalized.get("raw_content")
    if "item_id" in normalized and "id" not in normalized:
        normalized["id"] = normalized.get("item_id")
    if "output_preview" in normalized and "outputPreview" not in normalized:
        normalized["outputPreview"] = normalized.get("output_preview")
    if "aggregated_output" in normalized and "aggregatedOutput" not in normalized:
        normalized["aggregatedOutput"] = normalized.get("aggregated_output")
    if "exit_code" in normalized and "exitCode" not in normalized:
        normalized["exitCode"] = normalized.get("exit_code")
    return normalized


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [_flatten_text(item) for item in value]
        return "\n".join(part for part in parts if part).strip()
    if isinstance(value, dict):
        parts = [_flatten_text(value.get("text")), _flatten_text(value.get("content")), _flatten_text(value.get("summary"))]
        return "\n".join(part for part in parts if part).strip()
    return ""


def _normalize_thread_status(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("type", "status", "state", "name"):
            normalized = str(value.get(key) or "").strip()
            if normalized:
                return normalized
    if isinstance(value, list):
        parts = [_normalize_thread_status(item) for item in value]
        return " / ".join(part for part in parts if part).strip()
    return str(value or "").strip()


class CodexSemanticMapper:
    def map(
        self,
        envelope: CodexRawEventEnvelope,
        descriptor: CodexEventDescriptor,
        state: Any,
    ) -> tuple[CodexSemanticEvent, ...]:
        if descriptor.policy == "ignore":
            if envelope.method == "item/reasoning/summaryPartAdded":
                self._reasoning_state(state, envelope.item_id)
            return ()
        if descriptor.semantic_name == "session.started":
            return (self._map_session_started(envelope, descriptor),)
        if descriptor.semantic_name == "turn.started":
            return (self._map_turn_started(envelope, descriptor),)
        if descriptor.semantic_name == "assistant.delta":
            return (self._map_assistant_delta(envelope, descriptor, state),)
        if descriptor.semantic_name == "reasoning.delta":
            return self._map_reasoning(envelope, descriptor, state)
        if descriptor.semantic_name in {"plan.delta", "plan.updated"}:
            return self._map_plan(envelope, descriptor, state)
        if descriptor.semantic_name == "tool.progress":
            return (self._map_tool_progress(envelope, descriptor, state),)
        if descriptor.semantic_name == "terminal.interaction":
            return (self._map_terminal_interaction(envelope, descriptor),)
        if descriptor.semantic_name == "approval.resolved":
            return (self._map_approval_resolved(envelope, descriptor),)
        if descriptor.semantic_name == "item.started":
            return self._map_item_started(envelope, descriptor, state)
        if descriptor.semantic_name == "item.completed":
            return self._map_item_completed(envelope, descriptor, state)
        if descriptor.semantic_name == "usage.updated":
            usage = self._extract_usage(envelope.params)
            if usage is None:
                return ()
            state.usage = usage
            return (
                CodexSemanticEvent(
                    semantic_name="usage.updated",
                    policy=descriptor.policy,
                    source_method=envelope.method,
                    source_route=envelope.route,
                    thread_id=envelope.thread_id,
                    turn_id=envelope.turn_id,
                    dedupe_key=self._usage_dedupe_key(envelope, usage),
                    usage=usage,
                    payload={},
                ),
            )
        if descriptor.semantic_name in {"turn.terminal", "turn.error"}:
            terminal = self._map_terminal(envelope, descriptor, state)
            return () if terminal is None else (terminal,)
        if descriptor.policy == "system":
            return self._map_system_event(envelope, descriptor, state)
        return (self._observe_event(envelope, descriptor, title=f"Unexpected backend event: {envelope.method}"),)

    def _map_session_started(self, envelope: CodexRawEventEnvelope, descriptor: CodexEventDescriptor) -> CodexSemanticEvent:
        thread = envelope.params.get("thread") if isinstance(envelope.params.get("thread"), dict) else {}
        native_session_id = str(
            envelope.params.get("threadId")
            or thread.get("id")
            or envelope.params.get("conversationId")
            or envelope.thread_id
            or ""
        )
        title = str(thread.get("name") or thread.get("title") or thread.get("preview") or "")
        return CodexSemanticEvent(
            semantic_name="session.started",
            policy=descriptor.policy,
            source_method=envelope.method,
            source_route=envelope.route,
            thread_id=native_session_id,
            turn_id=envelope.turn_id,
            dedupe_key=f"session.started:{native_session_id}",
            payload={"native_session_id": native_session_id, "title": title},
        )

    def _map_turn_started(self, envelope: CodexRawEventEnvelope, descriptor: CodexEventDescriptor) -> CodexSemanticEvent:
        return CodexSemanticEvent(
            semantic_name="turn.started",
            policy=descriptor.policy,
            source_method=envelope.method,
            source_route=envelope.route,
            thread_id=envelope.thread_id,
            turn_id=envelope.turn_id,
            dedupe_key=f"turn.started:{envelope.thread_id}:{envelope.turn_id}",
        )

    def _map_assistant_delta(self, envelope: CodexRawEventEnvelope, descriptor: CodexEventDescriptor, state: Any) -> CodexSemanticEvent:
        delta = self._delta(envelope.params)
        text = f"{state.agent_text_by_id.get(envelope.item_id, '')}{delta}"
        state.agent_text_by_id[envelope.item_id] = text
        state.final_text = text or state.final_text
        return CodexSemanticEvent(
            semantic_name="assistant.delta",
            policy=descriptor.policy,
            source_method=envelope.method,
            source_route=envelope.route,
            thread_id=envelope.thread_id,
            turn_id=envelope.turn_id,
            item_id=envelope.item_id,
            dedupe_key=f"assistant.delta:{envelope.thread_id}:{envelope.turn_id}:{envelope.item_id}:{delta}",
            text=delta,
        )

    def _map_reasoning(
        self,
        envelope: CodexRawEventEnvelope,
        descriptor: CodexEventDescriptor,
        state: Any,
    ) -> tuple[CodexSemanticEvent, ...]:
        if envelope.method in {"item/reasoning/textDelta", "codex/event/reasoning_content_delta"}:
            index = self._int_field(envelope.params, "contentIndex", "content_index")
            reasoning = self._reasoning_state(state, envelope.item_id)
            reasoning.append_content(index, self._delta(envelope.params))
            return (
                CodexSemanticEvent(
                    semantic_name="reasoning.delta",
                    policy=descriptor.policy,
                    source_method=envelope.method,
                    source_route=envelope.route,
                    thread_id=envelope.thread_id,
                    turn_id=envelope.turn_id,
                    item_id=envelope.item_id,
                    dedupe_key=f"reasoning.delta:content:{envelope.thread_id}:{envelope.turn_id}:{envelope.item_id}:{index}:{self._delta(envelope.params)}",
                    text=self._combined_reasoning_text(state),
                ),
            )
        if envelope.method in {"item/reasoning/summaryTextDelta", "codex/event/reasoning_summary_text_delta"}:
            index = self._int_field(envelope.params, "summaryIndex", "summary_index")
            reasoning = self._reasoning_state(state, envelope.item_id)
            reasoning.append_summary(index, self._delta(envelope.params))
            return (
                CodexSemanticEvent(
                    semantic_name="reasoning.delta",
                    policy=descriptor.policy,
                    source_method=envelope.method,
                    source_route=envelope.route,
                    thread_id=envelope.thread_id,
                    turn_id=envelope.turn_id,
                    item_id=envelope.item_id,
                    dedupe_key=f"reasoning.delta:summary:{envelope.thread_id}:{envelope.turn_id}:{envelope.item_id}:{index}:{self._delta(envelope.params)}",
                    text=self._combined_reasoning_text(state),
                ),
            )
        return (self._observe_event(envelope, descriptor, title=f"Unexpected backend event: {envelope.method}"),)

    def _map_plan(
        self,
        envelope: CodexRawEventEnvelope,
        descriptor: CodexEventDescriptor,
        state: Any,
    ) -> tuple[CodexSemanticEvent, ...]:
        if envelope.method == "item/plan/delta":
            return (
                CodexSemanticEvent(
                    semantic_name="plan.delta",
                    policy="observe",
                    source_method=envelope.method,
                    source_route=envelope.route,
                    thread_id=envelope.thread_id,
                    turn_id=envelope.turn_id,
                    item_id=envelope.item_id,
                    message=self._delta(envelope.params),
                    payload={"item_id": envelope.item_id, "title": "Plan delta"},
                ),
            )
        raw_steps = envelope.params.get("plan") if isinstance(envelope.params.get("plan"), list) else []
        if not raw_steps and envelope.method == "codex/event/plan_update":
            msg = envelope.params.get("msg") if isinstance(envelope.params.get("msg"), dict) else {}
            raw_steps = msg.get("plan") if isinstance(msg.get("plan"), list) else []
        if raw_steps:
            steps = tuple(self._to_plan_step(item) for item in raw_steps if isinstance(item, dict))
            explanation = str(envelope.params.get("explanation") or "")
            return (
                CodexSemanticEvent(
                    semantic_name="plan.updated",
                    policy=descriptor.policy,
                    source_method=envelope.method,
                    source_route=envelope.route,
                    thread_id=envelope.thread_id,
                    turn_id=envelope.turn_id,
                    dedupe_key=f"plan.updated:{envelope.thread_id}:{envelope.turn_id}:{steps}:{explanation}",
                    steps=steps,
                    explanation=explanation,
                ),
            )
        item = self._extract_event_item(envelope.params)
        text = _flatten_text(item.get("text") or item.get("content") or envelope.params.get("text"))
        if not text:
            return ()
        return (
            CodexSemanticEvent(
                semantic_name="plan.updated",
                policy=descriptor.policy,
                source_method=envelope.method,
                source_route=envelope.route,
                thread_id=envelope.thread_id,
                turn_id=envelope.turn_id,
                item_id=str(item.get("id") or envelope.item_id),
                dedupe_key=f"plan.updated:{envelope.thread_id}:{envelope.turn_id}:{text}",
                steps=(PlanStep(step=text, status="completed"),),
                payload={"item_id": str(item.get('id') or envelope.item_id)},
            ),
        )

    def _map_tool_progress(
        self,
        envelope: CodexRawEventEnvelope,
        descriptor: CodexEventDescriptor,
        state: Any,
    ) -> CodexSemanticEvent:
        if envelope.method == "item/mcpToolCall/progress":
            detail = _flatten_text(envelope.params.get("content"))
            return CodexSemanticEvent(
                semantic_name="tool.progress",
                policy=descriptor.policy,
                source_method=envelope.method,
                source_route=envelope.route,
                thread_id=envelope.thread_id,
                turn_id=envelope.turn_id,
                tool_id=envelope.item_id,
                detail=detail,
                dedupe_key=f"tool.progress:mcp:{envelope.thread_id}:{envelope.turn_id}:{envelope.item_id}:{detail}",
                payload={"content": envelope.params.get("content")},
            )
        storage = state.file_change_output_by_id if envelope.method == "item/fileChange/outputDelta" else state.command_output_by_id
        delta = self._delta(envelope.params)
        storage[envelope.item_id] = f"{storage.get(envelope.item_id, '')}{delta}"
        return CodexSemanticEvent(
            semantic_name="tool.progress",
            policy=descriptor.policy,
            source_method=envelope.method,
            source_route=envelope.route,
            thread_id=envelope.thread_id,
            turn_id=envelope.turn_id,
            tool_id=envelope.item_id,
            detail=delta,
            dedupe_key=f"tool.progress:{envelope.thread_id}:{envelope.turn_id}:{envelope.item_id}:{delta}",
        )

    def _map_approval_resolved(self, envelope: CodexRawEventEnvelope, descriptor: CodexEventDescriptor) -> CodexSemanticEvent:
        return CodexSemanticEvent(
            semantic_name="approval.resolved",
            policy=descriptor.policy,
            source_method=envelope.method,
            source_route=envelope.route,
            thread_id=envelope.thread_id,
            turn_id=envelope.turn_id,
            approval_id=str(envelope.params.get("requestId") or ""),
        )

    def _map_terminal_interaction(
        self,
        envelope: CodexRawEventEnvelope,
        descriptor: CodexEventDescriptor,
    ) -> CodexSemanticEvent:
        process_id = str(envelope.params.get("processId") or "").strip()
        stdin = str(envelope.params.get("stdin") or "")
        item_id = str(envelope.params.get("itemId") or envelope.item_id)
        return CodexSemanticEvent(
            semantic_name="terminal.interaction",
            policy=descriptor.policy,
            source_method=envelope.method,
            source_route=envelope.route,
            thread_id=envelope.thread_id,
            turn_id=envelope.turn_id,
            item_id=item_id,
            dedupe_key=f"terminal.interaction:{envelope.thread_id}:{envelope.turn_id}:{item_id}:{process_id}:{stdin}",
            message="Command terminal interaction",
            payload={
                "title": "Command terminal interaction",
                "item_id": item_id,
                "process_id": process_id,
                "stdin": stdin,
            },
        )

    def _map_item_started(
        self,
        envelope: CodexRawEventEnvelope,
        descriptor: CodexEventDescriptor,
        state: Any,
    ) -> tuple[CodexSemanticEvent, ...]:
        item = self._extract_event_item(envelope.params)
        item_type = str(item.get("type") or "")
        item_id = str(item.get("id") or envelope.item_id)
        if item_type == "reasoning":
            self._reasoning_state(state, item_id)
            return ()
        if item_type == "userMessage":
            return ()
        if item_type in {"agentMessage", "plan"}:
            return ()
        tool = self._to_tool_state(item, status="running", state=state)
        if tool is None:
            return (self._observe_unexpected_item(envelope, item, f"Unexpected backend item started: {item_type or 'unknown'}"),)
        return (
            CodexSemanticEvent(
                semantic_name="tool.started",
                policy="render",
                source_method=envelope.method,
                source_route=envelope.route,
                thread_id=envelope.thread_id,
                turn_id=envelope.turn_id,
                item_id=item_id,
                dedupe_key=f"tool.started:{envelope.thread_id}:{envelope.turn_id}:{item_id}",
                tool=tool,
            ),
        )

    def _map_item_completed(
        self,
        envelope: CodexRawEventEnvelope,
        descriptor: CodexEventDescriptor,
        state: Any,
    ) -> tuple[CodexSemanticEvent, ...]:
        item = self._extract_event_item(envelope.params)
        item_type = str(item.get("type") or "")
        item_id = str(item.get("id") or envelope.item_id)
        if item_type == "agentMessage":
            text = str(item.get("text") or state.agent_text_by_id.get(item_id, "")).strip()
            if not text:
                return ()
            state.final_text = text
            return (
                CodexSemanticEvent(
                    semantic_name="assistant.completed",
                    policy="render",
                    source_method=envelope.method,
                    source_route=envelope.route,
                    thread_id=envelope.thread_id,
                    turn_id=envelope.turn_id,
                    item_id=item_id,
                    dedupe_key=f"assistant.completed:{envelope.thread_id}:{envelope.turn_id}:{item_id}:{text}",
                    text=text,
                ),
            )
        if item_type == "reasoning":
            reasoning = self._reasoning_state(state, item_id)
            summary = item.get("summary")
            content = item.get("content")
            if isinstance(summary, list):
                reasoning.seed_summary([str(part) for part in summary])
            if isinstance(content, list):
                reasoning.seed_content([str(part) for part in content])
            text = self._combined_reasoning_text(state) or reasoning.text()
            if not text:
                return ()
            return (
                CodexSemanticEvent(
                    semantic_name="reasoning.delta",
                    policy="render",
                    source_method=envelope.method,
                    source_route=envelope.route,
                    thread_id=envelope.thread_id,
                    turn_id=envelope.turn_id,
                    item_id=item_id,
                    dedupe_key=f"reasoning.completed:{envelope.thread_id}:{envelope.turn_id}:{item_id}:{text}",
                    text=text,
                    payload={"completed": True, "item_id": item_id},
                ),
            )
        if item_type == "userMessage":
            return ()
        if item_type == "plan":
            text = _flatten_text(item.get("text") or item.get("content"))
            if not text:
                return ()
            return (
                CodexSemanticEvent(
                    semantic_name="plan.updated",
                    policy="render",
                    source_method=envelope.method,
                    source_route=envelope.route,
                    thread_id=envelope.thread_id,
                    turn_id=envelope.turn_id,
                    item_id=item_id,
                    dedupe_key=f"plan.updated:{envelope.thread_id}:{envelope.turn_id}:{item_id}:{text}",
                    steps=(PlanStep(step=text, status="completed"),),
                    payload={"item_id": item_id},
                ),
            )
        tool = self._to_tool_state(item, status="completed", state=state)
        if tool is None:
            return (self._observe_unexpected_item(envelope, item, f"Unexpected backend item completed: {item_type or 'unknown'}"),)
        return (
            CodexSemanticEvent(
                semantic_name="tool.completed",
                policy="render",
                source_method=envelope.method,
                source_route=envelope.route,
                thread_id=envelope.thread_id,
                turn_id=envelope.turn_id,
                item_id=item_id,
                dedupe_key=f"tool.completed:{envelope.thread_id}:{envelope.turn_id}:{item_id}",
                tool=tool,
            ),
        )

    def _map_terminal(
        self,
        envelope: CodexRawEventEnvelope,
        descriptor: CodexEventDescriptor,
        state: Any,
    ) -> CodexSemanticEvent | None:
        if envelope.method == "error":
            if envelope.params.get("willRetry"):
                return None
            error = envelope.params.get("error") if isinstance(envelope.params.get("error"), dict) else {}
            return CodexSemanticEvent(
                semantic_name="turn.failed",
                policy="system",
                source_method=envelope.method,
                source_route=envelope.route,
                thread_id=envelope.thread_id,
                turn_id=envelope.turn_id,
                terminal_kind="failed",
                message=str(error.get("message") or envelope.params),
            )
        if envelope.method == "codex/event/turn_aborted":
            msg = envelope.params.get("msg") if isinstance(envelope.params.get("msg"), dict) else {}
            status = str(msg.get("status") or "interrupted")
            message = str(msg.get("error", {}).get("message") if isinstance(msg.get("error"), dict) else msg.get("error") or "interrupted")
            semantic_name = "turn.interrupted" if status == "interrupted" else "turn.failed"
            terminal_kind = "interrupted" if semantic_name == "turn.interrupted" else "failed"
            return CodexSemanticEvent(
                semantic_name=semantic_name,
                policy="system",
                source_method=envelope.method,
                source_route=envelope.route,
                thread_id=envelope.thread_id,
                turn_id=envelope.turn_id,
                terminal_kind=terminal_kind,
                message=message,
            )
        turn = envelope.params.get("turn") if isinstance(envelope.params.get("turn"), dict) else {}
        msg = envelope.params.get("msg") if isinstance(envelope.params.get("msg"), dict) else {}
        if not turn:
            turn = {"status": msg.get("status") or "completed", "error": msg.get("error")}
        last_agent_message = str(msg.get("last_agent_message") or msg.get("lastAgentMessage") or "").strip()
        final_text = (state.final_text or last_agent_message).strip()
        status = str(turn.get("status") or "")
        if status == "completed":
            return CodexSemanticEvent(
                semantic_name="turn.completed",
                policy="system",
                source_method=envelope.method,
                source_route=envelope.route,
                thread_id=envelope.thread_id,
                turn_id=envelope.turn_id,
                terminal_kind="completed",
                final_text=final_text,
                usage=state.usage,
            )
        if status == "interrupted":
            error = turn.get("error") if isinstance(turn.get("error"), dict) else {}
            return CodexSemanticEvent(
                semantic_name="turn.interrupted",
                policy="system",
                source_method=envelope.method,
                source_route=envelope.route,
                thread_id=envelope.thread_id,
                turn_id=envelope.turn_id,
                terminal_kind="interrupted",
                message=str(error.get("message") or "interrupted"),
            )
        error = turn.get("error") if isinstance(turn.get("error"), dict) else {}
        return CodexSemanticEvent(
            semantic_name="turn.failed",
            policy="system",
            source_method=envelope.method,
            source_route=envelope.route,
            thread_id=envelope.thread_id,
            turn_id=envelope.turn_id,
            terminal_kind="failed",
            message=str(error.get("message") or f"Turn {status or 'failed'}"),
        )

    def _observe_event(
        self,
        envelope: CodexRawEventEnvelope,
        descriptor: CodexEventDescriptor,
        *,
        title: str,
    ) -> CodexSemanticEvent:
        return CodexSemanticEvent(
            semantic_name=descriptor.semantic_name,
            policy="observe",
            source_method=envelope.method,
            source_route=envelope.route,
            thread_id=envelope.thread_id,
            turn_id=envelope.turn_id,
            item_id=envelope.item_id,
            level="warning",
            message=title,
            payload={
                "fallback": True,
                "observe": True,
                "title": title,
                "raw_event": {"method": envelope.method, "params": envelope.params},
            },
        )

    def _observe_unexpected_item(
        self,
        envelope: CodexRawEventEnvelope,
        item: dict[str, Any],
        title: str,
    ) -> CodexSemanticEvent:
        return CodexSemanticEvent(
            semantic_name="backend.observe",
            policy="observe",
            source_method=envelope.method,
            source_route=envelope.route,
            thread_id=envelope.thread_id,
            turn_id=envelope.turn_id,
            item_id=envelope.item_id,
            level="warning",
            message=title,
            payload={
                "fallback": True,
                "observe": True,
                "title": title,
                "raw_event": {"method": envelope.method, "params": envelope.params, "item": item},
            },
        )

    def _map_system_event(
        self,
        envelope: CodexRawEventEnvelope,
        descriptor: CodexEventDescriptor,
        state: Any,
    ) -> tuple[CodexSemanticEvent, ...]:
        payload = self._update_system_snapshot(envelope, descriptor, state)
        if not payload:
            return ()
        dedupe_parts = [descriptor.semantic_name, envelope.thread_id, envelope.turn_id]
        if descriptor.semantic_name == "thread.status.changed":
            dedupe_parts.append(str(payload.get("status") or ""))
        elif descriptor.semantic_name == "account.rate_limits.updated":
            dedupe_parts.append(str(payload.get("rate_limits") or {}))
        elif descriptor.semantic_name == "skills.changed":
            dedupe_parts.append(str(payload.get("version") or ""))
            dedupe_parts.append(str(payload.get("skills") or ()))
        elif descriptor.semantic_name == "thread.diff.updated":
            dedupe_parts.append(str(payload.get("diff_id") or ""))
        return (
            CodexSemanticEvent(
                semantic_name=descriptor.semantic_name,
                policy=descriptor.policy,
                source_method=envelope.method,
                source_route=envelope.route,
                thread_id=envelope.thread_id,
                turn_id=envelope.turn_id,
                dedupe_key=":".join(dedupe_parts),
                payload=payload,
            ),
        )

    def _update_system_snapshot(
        self,
        envelope: CodexRawEventEnvelope,
        descriptor: CodexEventDescriptor,
        state: Any,
    ) -> dict[str, Any]:
        snapshot = getattr(state, "system_snapshot", None)
        if snapshot is None:
            snapshot = {}
        if descriptor.semantic_name == "thread.status.changed":
            status = _normalize_thread_status(envelope.params.get("status"))
            snapshot["thread_status"] = status
            return {"status": status}
        if descriptor.semantic_name == "thread.diff.updated":
            diff_id = str(envelope.params.get("diffId") or envelope.params.get("diff_id") or "")
            snapshot["last_diff_id"] = diff_id
            return {"diff_id": diff_id}
        if descriptor.semantic_name == "skills.changed":
            version = str(envelope.params.get("version") or envelope.params.get("skillsVersion") or "")
            skills = envelope.params.get("skills") if isinstance(envelope.params.get("skills"), list) else []
            normalized_skills = tuple(str(skill) for skill in skills if str(skill).strip())
            snapshot["skills_version"] = version
            snapshot["skills"] = normalized_skills
            return {"version": version, "skills": normalized_skills}
        if descriptor.semantic_name == "account.rate_limits.updated":
            rate_limits = envelope.params.get("rateLimits") if isinstance(envelope.params.get("rateLimits"), dict) else envelope.params
            snapshot["rate_limits_payload"] = dict(rate_limits)
            return {"rate_limits": dict(rate_limits)}
        return {}

    def _usage_dedupe_key(self, envelope: CodexRawEventEnvelope, usage: UsageSnapshot) -> str:
        return (
            f"usage.updated:{envelope.thread_id}:{envelope.turn_id}:"
            f"{usage.input_tokens}:{usage.cached_input_tokens}:{usage.output_tokens}:"
            f"{usage.reasoning_output_tokens}:{usage.total_tokens}:{usage.context_window}"
        )

    def _extract_event_item(self, params: dict[str, Any]) -> dict[str, Any]:
        item = params.get("item") if isinstance(params.get("item"), dict) else {}
        if item:
            return _normalize_event_item(item)
        msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
        event_item = msg.get("item") if isinstance(msg.get("item"), dict) else {}
        return _normalize_event_item(event_item)

    def _item_id(self, params: dict[str, Any]) -> str:
        msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
        return str(params.get("itemId") or msg.get("item_id") or msg.get("itemId") or "")

    def _delta(self, params: dict[str, Any]) -> str:
        msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
        return str(params.get("delta") or msg.get("delta") or "")

    def _int_field(self, params: dict[str, Any], primary: str, alias: str) -> int:
        msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
        raw = params.get(primary) or msg.get(alias) or msg.get(primary) or 0
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    def _reasoning_state(self, state: Any, item_id: str) -> Any:
        if item_id and item_id not in state.reasoning_order:
            state.reasoning_order.append(item_id)
        reasoning_state = state.reasoning_by_id.get(item_id)
        if reasoning_state is None:
            reasoning_state = type("_ReasoningShim", (), {})()
            reasoning_state.content_by_index = {}
            reasoning_state.summary_by_index = {}
            reasoning_state.append_content = lambda index, delta: reasoning_state.content_by_index.__setitem__(index, f"{reasoning_state.content_by_index.get(index, '')}{delta or ''}")
            reasoning_state.append_summary = lambda index, delta: reasoning_state.summary_by_index.__setitem__(index, f"{reasoning_state.summary_by_index.get(index, '')}{delta or ''}")
            reasoning_state.seed_content = lambda parts: reasoning_state.content_by_index.update({index: str(part) for index, part in enumerate(parts)})
            reasoning_state.seed_summary = lambda parts: reasoning_state.summary_by_index.update({index: str(part) for index, part in enumerate(parts)})
            reasoning_state.text = lambda: combine_indexed_text(reasoning_state.summary_by_index) or combine_indexed_text(reasoning_state.content_by_index)
            state.reasoning_by_id[item_id] = reasoning_state
        return reasoning_state

    def _combined_reasoning_text(self, state: Any) -> str:
        parts: list[str] = []
        for item_id in state.reasoning_order:
            text = self._reasoning_state(state, item_id).text().strip()
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()

    def _summarize_file_changes(self, item: dict[str, Any]) -> str:
        changes = item.get("changes") if isinstance(item.get("changes"), list) else []
        paths = [str(change.get("path") or "").strip() for change in changes if isinstance(change, dict)]
        return ", ".join(path for path in paths if path)

    def _to_plan_step(self, item: dict[str, Any]) -> PlanStep:
        step = str(item.get("step") or item.get("title") or item.get("content") or item.get("text") or "").strip()
        status = str(item.get("status") or "pending").strip() or "pending"
        if status not in {"pending", "in_progress", "completed"}:
            status = "pending"
        return PlanStep(step=step, status=status)  # type: ignore[arg-type]

    def _to_tool_state(self, item: dict[str, Any], *, status: str, state: Any) -> ToolState | None:
        item_type = str(item.get("type") or "")
        item_id = str(item.get("id") or "")
        if item_type == "commandExecution":
            command = str(item.get("command") or "")
            aggregated_output = str(item.get("aggregatedOutput") or state.command_output_by_id.get(item_id, ""))
            return ToolState(
                tool_id=item_id,
                kind="command",
                title=command or "Command",
                status=status,  # type: ignore[arg-type]
                preview=command,
                detail=aggregated_output,
                exit_code=item.get("exitCode") if isinstance(item.get("exitCode"), int) else None,
                provider_payload={"item_type": item_type, "status": item.get("status")},
            )
        if item_type == "webSearch":
            query = str(item.get("query") or "")
            return ToolState(
                tool_id=item_id,
                kind="web_search",
                title=query or "Web search",
                status=status,  # type: ignore[arg-type]
                preview=query,
                provider_payload={"item_type": item_type, "action": item.get("action"), "status": item.get("status")},
            )
        if item_type == "fileChange":
            return ToolState(
                tool_id=item_id,
                kind="file_change",
                title="File changes",
                status=status,  # type: ignore[arg-type]
                preview=self._summarize_file_changes(item),
                detail=state.file_change_output_by_id.get(item_id, ""),
                provider_payload={"item_type": item_type, "changes": item.get("changes"), "status": item.get("status")},
            )
        if item_type == "collabAgentToolCall":
            return ToolState(
                tool_id=item_id,
                kind="custom",
                title=str(item.get("tool") or "Collaborative agent"),
                status=status,  # type: ignore[arg-type]
                preview=str(item.get("prompt") or ""),
                provider_payload={
                    "item_type": item_type,
                    "status": item.get("status"),
                    "senderThreadId": item.get("senderThreadId"),
                    "receiverThreadIds": item.get("receiverThreadIds"),
                    "agentsStates": item.get("agentsStates"),
                },
            )
        if item_type == "mcpToolCall":
            return ToolState(
                tool_id=item_id,
                kind="mcp",
                title=str(item.get("server") or item.get("tool") or "MCP tool"),
                status=status,  # type: ignore[arg-type]
                preview=_flatten_text(item.get("content")),
                provider_payload={"item_type": item_type, "status": item.get("status")},
            )
        return None

    def _extract_usage(self, params: dict[str, Any]) -> UsageSnapshot | None:
        token_usage = params.get("tokenUsage") if isinstance(params.get("tokenUsage"), dict) else {}
        if token_usage:
            last = (
                token_usage.get("last")
                if isinstance(token_usage.get("last"), dict)
                else token_usage.get("total")
                if isinstance(token_usage.get("total"), dict)
                else {}
            )
            return UsageSnapshot(
                input_tokens=last.get("inputTokens"),
                cached_input_tokens=last.get("cachedInputTokens"),
                output_tokens=last.get("outputTokens"),
                reasoning_output_tokens=last.get("reasoningOutputTokens"),
                total_tokens=last.get("totalTokens"),
                context_window=token_usage.get("modelContextWindow"),
            )
        msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
        info = msg.get("info") if isinstance(msg.get("info"), dict) else {}
        usage = info.get("last_token_usage") if isinstance(info.get("last_token_usage"), dict) else {}
        if not usage:
            usage = info.get("total_token_usage") if isinstance(info.get("total_token_usage"), dict) else {}
        if not usage:
            return None
        return UsageSnapshot(
            input_tokens=usage.get("input_tokens"),
            cached_input_tokens=usage.get("cached_input_tokens"),
            output_tokens=usage.get("output_tokens"),
            reasoning_output_tokens=usage.get("reasoning_output_tokens"),
            total_tokens=usage.get("total_tokens"),
            context_window=info.get("model_context_window"),
        )
