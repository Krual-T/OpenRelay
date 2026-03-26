from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from openrelay.agent_runtime import ApprovalDecision, ApprovalRequest, ApprovalRequestedEvent, RuntimeEvent

from .event_deduper import CodexSemanticDeduper
from .event_registry import CodexEventRegistry
from .runtime_projector import CodexRuntimeEventProjector
from .semantic_events import CodexRawEventEnvelope, CodexTerminalState
from .semantic_mapper import CodexSemanticMapper, _flatten_text


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
        parts: list[str] = []
        for source in (self.summary_by_index, self.content_by_index):
            values = [str(source.get(index) or "").strip() for index in sorted(source)]
            values = [value for value in values if value]
            if values:
                parts = values
                break
        return "\n\n".join(parts).strip()


@dataclass(slots=True)
class CodexTurnState:
    agent_text_by_id: dict[str, str] = field(default_factory=dict)
    agent_phase_by_id: dict[str, str] = field(default_factory=dict)
    command_output_by_id: dict[str, str] = field(default_factory=dict)
    file_change_output_by_id: dict[str, str] = field(default_factory=dict)
    reasoning_by_id: dict[str, _ReasoningItemState] = field(default_factory=dict)
    reasoning_order: list[str] = field(default_factory=list)
    usage: Any = None
    final_text: str = ""
    seen_semantic_keys: set[str] = field(default_factory=set)
    terminal: CodexTerminalState = field(default_factory=CodexTerminalState)
    system_snapshot: dict[str, Any] = field(
        default_factory=lambda: {
            "thread_status": "",
            "latest_diff": "",
            "skills_version": "",
            "skills": (),
            "rate_limits_payload": {},
        }
    )


class CodexProtocolMapper:
    def __init__(
        self,
        session_id: str,
        native_session_id: str = "",
        turn_id: str = "",
    ) -> None:
        self.session_id = session_id
        self.native_session_id = native_session_id
        self.turn_id = turn_id
        self.registry = CodexEventRegistry()
        self.semantic_mapper = CodexSemanticMapper()
        self.deduper = CodexSemanticDeduper()
        self.projector = CodexRuntimeEventProjector(backend="codex", session_id=session_id)

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
        envelope = self._build_envelope(method, params)
        if envelope is None:
            return ()
        descriptor = self.registry.lookup(method)
        if descriptor is None:
            return (self._observe_unknown_event(envelope),)
        semantic_events = self.semantic_mapper.map(envelope, descriptor, state)
        runtime_events: list[RuntimeEvent] = []
        for semantic_event in semantic_events:
            if not self.deduper.accept(semantic_event, state):
                continue
            if semantic_event.turn_id:
                self.turn_id = semantic_event.turn_id
            runtime_events.extend(self.projector.project(semantic_event))
        return tuple(runtime_events)

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

        return ApprovalRequestedEvent(
            backend="codex",
            session_id=self.session_id,
            turn_id=self.turn_id or turn_id,
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

    def _build_turn_input(self, turn_input: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if str(turn_input.text or "").strip():
            items.append({"type": "text", "text": turn_input.text})
        for path in turn_input.local_image_paths:
            items.append({"type": "localImage", "path": path})
        return items

    def _build_envelope(self, method: str, params: dict[str, Any]) -> CodexRawEventEnvelope | None:
        thread_id, turn_id = self._message_identity(params)
        if not self._matches(thread_id, turn_id):
            return None
        item_id = self._item_id(params)
        envelope = CodexRawEventEnvelope(
            method=method,
            route="v2",
            params=params,
            thread_id=thread_id,
            turn_id=turn_id,
            item_id=item_id,
        )
        if turn_id:
            self.turn_id = turn_id
        if thread_id:
            self.native_session_id = thread_id
        return envelope

    def _observe_unknown_event(self, envelope: CodexRawEventEnvelope) -> RuntimeEvent:
        return self.projector.project(
            self.semantic_mapper._observe_event(
                envelope,
                type("_UnknownDescriptor", (), {"semantic_name": "backend.observe"})(),
                title=f"Unexpected backend event: {envelope.method}",
            )
        )[0]

    def _matches(self, thread_id: str, turn_id: str) -> bool:
        if self.native_session_id and thread_id and thread_id != self.native_session_id:
            return False
        if self.turn_id and turn_id and turn_id != self.turn_id:
            return False
        return True

    def _message_identity(self, params: dict[str, Any]) -> tuple[str, str]:
        thread = params.get("thread") if isinstance(params.get("thread"), dict) else {}
        turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
        thread_id = str(
            params.get("threadId")
            or thread.get("id")
            or self.native_session_id
            or ""
        )
        turn_id = str(
            params.get("turnId")
            or turn.get("id")
            or self.turn_id
            or ""
        )
        return thread_id, turn_id

    def _item_id(self, params: dict[str, Any]) -> str:
        item = params.get("item") if isinstance(params.get("item"), dict) else {}
        if item:
            return str(item.get("id") or item.get("item_id") or "")
        return str(params.get("itemId") or "")
