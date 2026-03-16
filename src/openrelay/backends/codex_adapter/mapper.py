from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from openrelay.agent_runtime import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalRequestedEvent,
    ApprovalResolvedEvent,
    AssistantCompletedEvent,
    AssistantDeltaEvent,
    BackendNoticeEvent,
    PlanStep,
    PlanUpdatedEvent,
    ReasoningDeltaEvent,
    RuntimeEvent,
    SessionStartedEvent,
    ToolCompletedEvent,
    ToolProgressEvent,
    ToolStartedEvent,
    ToolState,
    TurnCompletedEvent,
    TurnFailedEvent,
    TurnInterruptedEvent,
    TurnStartedEvent,
    UsageSnapshot,
    UsageUpdatedEvent,
)


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


@dataclass(slots=True)
class _ReasoningItemState:
    content_by_index: dict[int, str] = field(default_factory=dict)
    summary_by_index: dict[int, str] = field(default_factory=dict)

    def append_content(self, index: int, delta: str) -> None:
        self.content_by_index[index] = f"{self.content_by_index.get(index, '')}{delta or ''}"

    def append_summary(self, index: int, delta: str) -> None:
        self.summary_by_index[index] = f"{self.summary_by_index.get(index, '')}{delta or ''}"

    def seed_content(self, parts: list[str]) -> None:
        for index, part in enumerate(parts):
            self.content_by_index[index] = str(part)

    def seed_summary(self, parts: list[str]) -> None:
        for index, part in enumerate(parts):
            self.summary_by_index[index] = str(part)

    def text(self) -> str:
        return combine_indexed_text(self.summary_by_index) or combine_indexed_text(self.content_by_index)


@dataclass(slots=True)
class CodexTurnState:
    agent_text_by_id: dict[str, str] = field(default_factory=dict)
    command_output_by_id: dict[str, str] = field(default_factory=dict)
    file_change_output_by_id: dict[str, str] = field(default_factory=dict)
    reasoning_by_id: dict[str, _ReasoningItemState] = field(default_factory=dict)
    reasoning_order: list[str] = field(default_factory=list)
    usage: UsageSnapshot | None = None
    final_text: str = ""


class CodexProtocolMapper:
    def __init__(self, session_id: str, native_session_id: str = "", turn_id: str = "") -> None:
        self.session_id = session_id
        self.native_session_id = native_session_id
        self.turn_id = turn_id
        self.last_delta_fingerprint: tuple[str, ...] | None = None
        self.last_delta_method = ""

    def build_thread_params(
        self,
        *,
        cwd: str,
        model: str | None,
        safety_mode: str,
        default_model: str,
    ) -> dict[str, Any]:
        params = {
            "cwd": cwd,
            "model": model or default_model or None,
            "sandbox": safety_mode,
            "approvalPolicy": "never",
        }
        return {key: value for key, value in params.items() if value not in {None, ""}}

    def build_turn_start_params(
        self,
        *,
        thread_id: str,
        turn_input: Any,
    ) -> dict[str, Any]:
        return {
            "threadId": thread_id,
            "cwd": turn_input.cwd,
            "approvalPolicy": "never",
            **({"model": turn_input.model} if turn_input.model else {}),
            "input": self._build_turn_input(turn_input),
        }

    def map_notification(
        self,
        method: str,
        params: dict[str, Any],
        state: CodexTurnState,
    ) -> tuple[RuntimeEvent, ...]:
        thread_id, turn_id = self._message_identity(params)
        if not self._matches(thread_id, turn_id):
            return ()
        if self._duplicate_delta_alias(method, params):
            return ()

        if method == "thread/started":
            return self._map_thread_started(params)
        if method == "turn/started":
            return self._map_turn_started(params)
        if method in {"item/agentMessage/delta", "codex/event/agent_message_content_delta"}:
            return self._map_agent_delta(params, state)
        if method in {"item/reasoning/textDelta", "codex/event/reasoning_content_delta"}:
            return self._map_reasoning_content_delta(params, state)
        if method in {"item/reasoning/summaryTextDelta", "codex/event/reasoning_summary_text_delta"}:
            return self._map_reasoning_summary_delta(params, state)
        if method == "item/reasoning/summaryPartAdded":
            self._reasoning_state(state, self._item_id(params))
            return ()
        if method == "item/plan/delta":
            return self._map_plan_delta(params)
        if method == "turn/plan/updated":
            return self._map_plan_updated(params)
        if method in {"item/commandExecution/outputDelta", "codex/event/command_output_delta"}:
            return self._map_tool_output_delta(params, storage=state.command_output_by_id)
        if method == "item/fileChange/outputDelta":
            return self._map_tool_output_delta(params, storage=state.file_change_output_by_id)
        if method == "item/commandExecution/terminalInteraction":
            return (
                self._event(
                    BackendNoticeEvent,
                    event_type="backend.notice",
                    message="Terminal interaction requested",
                    provider_payload={
                        "method": method,
                        "item_id": self._item_id(params),
                        "process_id": str(params.get("processId") or ""),
                        "stdin": str(params.get("stdin") or ""),
                    },
                ),
            )
        if method == "item/mcpToolCall/progress":
            return (
                self._event(
                    ToolProgressEvent,
                    event_type="tool.progress",
                    tool_id=self._item_id(params),
                    detail=_flatten_text(params.get("content")),
                    provider_payload={"method": method, "content": params.get("content")},
                ),
            )
        if method == "serverRequest/resolved":
            return (
                self._event(
                    ApprovalResolvedEvent,
                    event_type="approval.resolved",
                    approval_id=str(params.get("requestId") or ""),
                    provider_payload={"method": method},
                ),
            )
        if method in {"item/started", "codex/event/item_started"}:
            return self._map_item_started(method, params, state)
        if method in {"item/completed", "codex/event/item_completed"}:
            return self._map_item_completed(method, params, state)
        if method in {"thread/tokenUsage/updated", "codex/event/token_count"}:
            return self._map_token_usage_updated(method, params, state)
        if method in {"turn/completed", "codex/event/task_complete"}:
            return self._map_turn_completed(method, params, state)
        if method == "error" and not params.get("willRetry"):
            error = params.get("error") if isinstance(params.get("error"), dict) else {}
            return (
                self._event(
                    TurnFailedEvent,
                    event_type="turn.failed",
                    message=str(error.get("message") or params),
                    provider_payload={"method": method},
                ),
            )
        return ()

    def map_server_request(
        self,
        request_id: int | str,
        method: str,
        params: dict[str, Any],
    ) -> ApprovalRequestedEvent | None:
        thread_id = str(params.get("threadId") or "")
        turn_id = str(params.get("turnId") or "")
        if not self._matches(thread_id, turn_id):
            return None

        kind = "custom"
        title = "Approval Requested"
        description = ""
        options: tuple[str, ...] = ("accept", "decline", "cancel")
        if method == "item/commandExecution/requestApproval":
            kind = "command"
            title = "Command Approval Required"
            command = str(params.get("command") or "unknown command")
            cwd = str(params.get("cwd") or "").strip()
            reason = str(params.get("reason") or "").strip()
            lines = [f"Command: {command}"]
            if cwd:
                lines.append(f"CWD: {cwd}")
            if reason:
                lines.append(f"Reason: {reason}")
            description = "\n".join(lines)
            options = ("accept", "accept_for_session", "decline", "cancel")
            payload = {
                "request_id": request_id,
                "command": command,
                "cwd": cwd,
                "reason": reason,
                "command_actions": params.get("commandActions"),
            }
        elif method == "item/fileChange/requestApproval":
            kind = "file_change"
            title = "File Change Approval Required"
            grant_root = str(params.get("grantRoot") or "").strip()
            reason = str(params.get("reason") or "").strip()
            lines = ["Codex wants permission to apply file changes."]
            if grant_root:
                lines.append(f"Grant root: {grant_root}")
            if reason:
                lines.append(f"Reason: {reason}")
            description = "\n".join(lines)
            payload = {
                "request_id": request_id,
                "grant_root": grant_root,
                "reason": reason,
            }
        elif method == "item/permissions/requestApproval":
            kind = "permissions"
            title = "Additional Permissions Requested"
            reason = str(params.get("reason") or "").strip()
            permissions = params.get("permissions") if isinstance(params.get("permissions"), dict) else {}
            description = _flatten_text(permissions)
            if reason:
                description = f"{description}\nReason: {reason}".strip()
            options = ("accept", "accept_for_session", "decline", "cancel")
            payload = {
                "request_id": request_id,
                "reason": reason,
                "permissions": permissions,
            }
        elif method == "item/tool/requestUserInput":
            kind = "user_input"
            title = "User Input Requested"
            description = _flatten_text(params.get("questions"))
            options = ("custom", "cancel")
            payload = {
                "request_id": request_id,
                "input_kind": "tool_questions",
                "questions": params.get("questions") if isinstance(params.get("questions"), list) else [],
            }
        elif method == "mcpServer/elicitation/request":
            kind = "user_input"
            title = "External Input Requested"
            description = _flatten_text(params.get("message")) or _flatten_text(params.get("requestedSchema"))
            options = ("custom", "cancel")
            payload = {
                "request_id": request_id,
                "input_kind": "mcp_elicitation",
                "mode": str(params.get("mode") or ""),
                "message": params.get("message"),
                "url": params.get("url"),
                "requested_schema": params.get("requestedSchema"),
            }
        else:
            payload = {"request_id": request_id}

        return self._event(
            ApprovalRequestedEvent,
            event_type="approval.requested",
            request=ApprovalRequest(
                approval_id=str(request_id),
                session_id=self.session_id,
                turn_id=self.turn_id or turn_id,
                kind=kind,
                title=title,
                description=description,
                payload=payload,
                options=options,
                provider_payload={"method": method, "params": params},
            ),
        )

    def build_approval_response(self, request: ApprovalRequest, decision: ApprovalDecision) -> dict[str, Any]:
        method = str(request.provider_payload.get("method") or "")
        if method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
        }:
            if decision.decision == "accept_for_session":
                return {"decision": "acceptForSession"}
            if decision.decision in {"accept", "decline", "cancel"}:
                return {"decision": decision.decision}
            return dict(decision.payload)
        if method == "item/tool/requestUserInput":
            if decision.decision == "cancel":
                return {"answers": {}}
            return dict(decision.payload)
        if method == "mcpServer/elicitation/request":
            if decision.decision == "cancel":
                return {"action": "cancel"}
            return dict(decision.payload)
        return dict(decision.payload)

    def _map_thread_started(self, params: dict[str, Any]) -> tuple[RuntimeEvent, ...]:
        thread = params.get("thread") if isinstance(params.get("thread"), dict) else {}
        native_session_id = str(
            params.get("threadId")
            or thread.get("id")
            or params.get("conversationId")
            or self.native_session_id
            or ""
        )
        self.native_session_id = native_session_id
        title = str(thread.get("name") or thread.get("title") or thread.get("preview") or "")
        return (
            self._event(
                SessionStartedEvent,
                event_type="session.started",
                native_session_id=native_session_id,
                title=title,
                provider_payload={"native_session_id": native_session_id, "method": "thread/started"},
            ),
        )

    def _map_turn_started(self, params: dict[str, Any]) -> tuple[RuntimeEvent, ...]:
        turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
        msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
        if not turn:
            turn = msg.get("turn") if isinstance(msg.get("turn"), dict) else {}
        self.turn_id = str(params.get("turnId") or turn.get("id") or msg.get("turn_id") or self.turn_id or "")
        return (self._event(TurnStartedEvent, event_type="turn.started"),)

    def _map_agent_delta(self, params: dict[str, Any], state: CodexTurnState) -> tuple[RuntimeEvent, ...]:
        item_id = self._item_id(params)
        delta = self._delta(params)
        text = f"{state.agent_text_by_id.get(item_id, '')}{delta}"
        state.agent_text_by_id[item_id] = text
        state.final_text = text or state.final_text
        return (self._event(AssistantDeltaEvent, event_type="assistant.delta", delta=delta),)

    def _map_reasoning_content_delta(self, params: dict[str, Any], state: CodexTurnState) -> tuple[RuntimeEvent, ...]:
        item_id = self._item_id(params)
        index = self._int_field(params, "contentIndex", "content_index")
        reasoning = self._reasoning_state(state, item_id)
        reasoning.append_content(index, self._delta(params))
        return (self._event(ReasoningDeltaEvent, event_type="reasoning.delta", text=self._combined_reasoning_text(state)),)

    def _map_reasoning_summary_delta(self, params: dict[str, Any], state: CodexTurnState) -> tuple[RuntimeEvent, ...]:
        item_id = self._item_id(params)
        index = self._int_field(params, "summaryIndex", "summary_index")
        reasoning = self._reasoning_state(state, item_id)
        reasoning.append_summary(index, self._delta(params))
        return (self._event(ReasoningDeltaEvent, event_type="reasoning.delta", text=self._combined_reasoning_text(state)),)

    def _map_plan_delta(self, params: dict[str, Any]) -> tuple[RuntimeEvent, ...]:
        item_id = self._item_id(params)
        return (
            self._event(
                BackendNoticeEvent,
                event_type="backend.notice",
                message=self._delta(params),
                provider_payload={"method": "item/plan/delta", "item_id": item_id},
            ),
        )

    def _map_plan_updated(self, params: dict[str, Any]) -> tuple[RuntimeEvent, ...]:
        raw_steps = params.get("plan") if isinstance(params.get("plan"), list) else []
        steps = tuple(self._to_plan_step(item) for item in raw_steps if isinstance(item, dict))
        return (
            self._event(
                PlanUpdatedEvent,
                event_type="plan.updated",
                steps=steps,
                explanation=str(params.get("explanation") or ""),
                provider_payload={"method": "turn/plan/updated"},
            ),
        )

    def _map_tool_output_delta(self, params: dict[str, Any], *, storage: dict[str, str]) -> tuple[RuntimeEvent, ...]:
        item_id = self._item_id(params)
        delta = self._delta(params)
        storage[item_id] = f"{storage.get(item_id, '')}{delta}"
        return (
            self._event(
                ToolProgressEvent,
                event_type="tool.progress",
                tool_id=item_id,
                detail=delta,
                provider_payload={"method": "item/tool/outputDelta"},
            ),
        )

    def _map_item_started(
        self,
        method: str,
        params: dict[str, Any],
        state: CodexTurnState,
    ) -> tuple[RuntimeEvent, ...]:
        item = self._extract_event_item(params)
        item_type = str(item.get("type") or "")
        item_id = str(item.get("id") or "")
        if item_type == "reasoning":
            self._reasoning_state(state, item_id)
            return (
                self._event(
                    BackendNoticeEvent,
                    event_type="backend.notice",
                    message="Reasoning started",
                    provider_payload={"method": method, "item_id": item_id, "item_type": item_type},
                ),
            )
        tool = self._to_tool_state(item, status="running", state=state)
        if tool is None:
            return ()
        return (self._event(ToolStartedEvent, event_type="tool.started", tool=tool, provider_payload={"method": method}),)

    def _map_item_completed(
        self,
        method: str,
        params: dict[str, Any],
        state: CodexTurnState,
    ) -> tuple[RuntimeEvent, ...]:
        item = self._extract_event_item(params)
        item_type = str(item.get("type") or "")
        item_id = str(item.get("id") or "")
        if item_type == "agentMessage":
            text = str(item.get("text") or state.agent_text_by_id.get(item_id, "")).strip()
            if text:
                state.final_text = text
                return (
                    self._event(
                        AssistantCompletedEvent,
                        event_type="assistant.completed",
                        text=text,
                        provider_payload={"method": method, "item_id": item_id},
                    ),
                )
            return ()
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
                self._event(
                    ReasoningDeltaEvent,
                    event_type="reasoning.delta",
                    text=text,
                    provider_payload={"method": method, "item_id": item_id, "completed": True},
                ),
            )
        if item_type == "plan":
            text = _flatten_text(item.get("text") or item.get("content"))
            if not text:
                return ()
            return (
                self._event(
                    PlanUpdatedEvent,
                    event_type="plan.updated",
                    steps=(PlanStep(step=text, status="completed"),),
                    provider_payload={"method": method, "item_id": item_id},
                ),
            )
        tool = self._to_tool_state(item, status="completed", state=state)
        if tool is None:
            return ()
        return (self._event(ToolCompletedEvent, event_type="tool.completed", tool=tool, provider_payload={"method": method}),)

    def _map_token_usage_updated(
        self,
        method: str,
        params: dict[str, Any],
        state: CodexTurnState,
    ) -> tuple[RuntimeEvent, ...]:
        usage = self._extract_usage(params)
        if usage is None:
            return ()
        state.usage = usage
        return (self._event(UsageUpdatedEvent, event_type="usage.updated", usage=usage, provider_payload={"method": method}),)

    def _map_turn_completed(
        self,
        method: str,
        params: dict[str, Any],
        state: CodexTurnState,
    ) -> tuple[RuntimeEvent, ...]:
        turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
        msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
        if not turn:
            turn = {"status": msg.get("status") or "completed", "error": msg.get("error")}
        last_agent_message = str(msg.get("last_agent_message") or msg.get("lastAgentMessage") or "").strip()
        final_text = (state.final_text or last_agent_message).strip()
        status = str(turn.get("status") or "")
        if status == "completed":
            return (
                self._event(
                    TurnCompletedEvent,
                    event_type="turn.completed",
                    final_text=final_text,
                    usage=state.usage,
                    provider_payload={"method": method},
                ),
            )
        if status == "interrupted":
            return (
                self._event(
                    TurnInterruptedEvent,
                    event_type="turn.interrupted",
                    message=str(turn.get("error", {}).get("message") or "interrupted"),
                    provider_payload={"method": method},
                ),
            )
        return (
            self._event(
                TurnFailedEvent,
                event_type="turn.failed",
                message=str(turn.get("error", {}).get("message") or f"Turn {status or 'failed'}"),
                provider_payload={"method": method},
            ),
        )

    def _to_tool_state(
        self,
        item: dict[str, Any],
        *,
        status: str,
        state: CodexTurnState,
    ) -> ToolState | None:
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

    def _event(self, event_cls: type[RuntimeEvent], **kwargs: Any) -> RuntimeEvent:
        return event_cls(
            backend="codex",
            session_id=self.session_id,
            turn_id=self.turn_id,
            **kwargs,
        )

    def _extract_event_item(self, params: dict[str, Any]) -> dict[str, Any]:
        item = params.get("item") if isinstance(params.get("item"), dict) else {}
        if item:
            return _normalize_event_item(item)
        msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
        event_item = msg.get("item") if isinstance(msg.get("item"), dict) else {}
        return _normalize_event_item(event_item)

    def _matches(self, thread_id: str, turn_id: str) -> bool:
        if self.native_session_id and thread_id and thread_id != self.native_session_id:
            return False
        if self.turn_id and turn_id and turn_id != self.turn_id:
            return False
        return True

    def _message_identity(self, params: dict[str, Any]) -> tuple[str, str]:
        msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
        thread = params.get("thread") if isinstance(params.get("thread"), dict) else {}
        turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
        thread_id = str(
            params.get("threadId")
            or thread.get("id")
            or params.get("conversationId")
            or msg.get("thread_id")
            or msg.get("threadId")
            or self.native_session_id
            or ""
        )
        turn_id = str(
            params.get("turnId")
            or turn.get("id")
            or msg.get("turn_id")
            or msg.get("turnId")
            or params.get("id")
            or self.turn_id
            or ""
        )
        return thread_id, turn_id

    def _duplicate_delta_alias(self, method: str, params: dict[str, Any]) -> bool:
        delta = self._delta(params)
        fingerprint: tuple[str, ...] | None = None
        if method in {"item/agentMessage/delta", "codex/event/agent_message_content_delta"} and delta:
            fingerprint = ("agent", self._item_id(params), delta)
        elif method in {"item/reasoning/textDelta", "codex/event/reasoning_content_delta"} and delta:
            fingerprint = ("reasoning.content", self._item_id(params), str(self._int_field(params, "contentIndex", "content_index")), delta)
        elif method in {"item/reasoning/summaryTextDelta", "codex/event/reasoning_summary_text_delta"} and delta:
            fingerprint = ("reasoning.summary", self._item_id(params), str(self._int_field(params, "summaryIndex", "summary_index")), delta)
        if fingerprint is None:
            self.last_delta_fingerprint = None
            self.last_delta_method = ""
            return False
        is_duplicate = fingerprint == self.last_delta_fingerprint and method != self.last_delta_method
        self.last_delta_fingerprint = fingerprint
        self.last_delta_method = method
        return is_duplicate

    def _build_turn_input(self, turn_input: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if str(turn_input.text or "").strip():
            items.append({"type": "text", "text": turn_input.text})
        for path in turn_input.local_image_paths:
            items.append({"type": "localImage", "path": path})
        return items

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

    def _reasoning_state(self, state: CodexTurnState, item_id: str) -> _ReasoningItemState:
        if item_id and item_id not in state.reasoning_order:
            state.reasoning_order.append(item_id)
        reasoning_state = state.reasoning_by_id.get(item_id)
        if reasoning_state is None:
            reasoning_state = _ReasoningItemState()
            state.reasoning_by_id[item_id] = reasoning_state
        return reasoning_state

    def _combined_reasoning_text(self, state: CodexTurnState) -> str:
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
