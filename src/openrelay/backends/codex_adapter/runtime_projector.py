from __future__ import annotations

from typing import Any

from openrelay.agent_runtime import (
    ApprovalResolvedEvent,
    AssistantCompletedEvent,
    AssistantDeltaEvent,
    BackendNoticeEvent,
    PlanUpdatedEvent,
    RateLimitsUpdatedEvent,
    ReasoningDeltaEvent,
    RuntimeEvent,
    SessionStartedEvent,
    SkillsUpdatedEvent,
    TerminalInteraction,
    TerminalInteractionEvent,
    ThreadDiffUpdatedEvent,
    ThreadStatusUpdatedEvent,
    ToolCompletedEvent,
    ToolProgressEvent,
    ToolStartedEvent,
    TurnCompletedEvent,
    TurnFailedEvent,
    TurnInterruptedEvent,
    TurnStartedEvent,
    UsageUpdatedEvent,
)

from .semantic_events import CodexSemanticEvent


class CodexRuntimeEventProjector:
    def __init__(self, *, backend: str, session_id: str) -> None:
        self.backend = backend
        self.session_id = session_id

    def project(self, event: CodexSemanticEvent) -> tuple[RuntimeEvent, ...]:
        provider_payload = {
            **event.payload,
            "method": event.source_method,
            "route": event.source_route,
            "semantic_name": event.semantic_name,
            "classification": event.policy,
        }
        if event.semantic_name == "session.started":
            return (
                SessionStartedEvent(
                    backend=self.backend,  # type: ignore[arg-type]
                    session_id=self.session_id,
                    turn_id=event.turn_id,
                    event_type="session.started",
                    native_session_id=str(event.payload.get("native_session_id") or ""),
                    title=str(event.payload.get("title") or ""),
                    provider_payload=provider_payload,
                ),
            )
        if event.semantic_name == "turn.started":
            return (self._event(TurnStartedEvent, event.turn_id, "turn.started", provider_payload),)
        if event.semantic_name == "assistant.delta":
            return (self._event(AssistantDeltaEvent, event.turn_id, "assistant.delta", provider_payload, delta=event.text),)
        if event.semantic_name == "assistant.completed":
            return (self._event(AssistantCompletedEvent, event.turn_id, "assistant.completed", provider_payload, text=event.text),)
        if event.semantic_name == "reasoning.delta":
            return (self._event(ReasoningDeltaEvent, event.turn_id, "reasoning.delta", provider_payload, text=event.text),)
        if event.semantic_name == "plan.updated":
            return (
                self._event(
                    PlanUpdatedEvent,
                    event.turn_id,
                    "plan.updated",
                    provider_payload,
                    steps=event.steps,
                    explanation=event.explanation,
                ),
            )
        if event.semantic_name == "tool.started" and event.tool is not None:
            return (self._event(ToolStartedEvent, event.turn_id, "tool.started", provider_payload, tool=event.tool),)
        if event.semantic_name == "tool.progress":
            return (
                self._event(
                    ToolProgressEvent,
                    event.turn_id,
                    "tool.progress",
                    provider_payload,
                    tool_id=event.tool_id,
                    detail=event.detail,
                ),
            )
        if event.semantic_name == "terminal.interaction":
            return (
                self._event(
                    TerminalInteractionEvent,
                    event.turn_id,
                    "terminal.interaction",
                    provider_payload,
                    interaction=TerminalInteraction(
                        item_id=str(event.payload.get("item_id") or event.item_id),
                        process_id=str(event.payload.get("process_id") or ""),
                        stdin=str(event.payload.get("stdin") or ""),
                    ),
                ),
            )
        if event.semantic_name == "tool.completed" and event.tool is not None:
            return (self._event(ToolCompletedEvent, event.turn_id, "tool.completed", provider_payload, tool=event.tool),)
        if event.semantic_name == "approval.resolved":
            return (
                self._event(
                    ApprovalResolvedEvent,
                    event.turn_id,
                    "approval.resolved",
                    provider_payload,
                    approval_id=event.approval_id,
                ),
            )
        if event.semantic_name == "usage.updated" and event.usage is not None:
            return (self._event(UsageUpdatedEvent, event.turn_id, "usage.updated", provider_payload, usage=event.usage),)
        if event.semantic_name == "thread.status.changed":
            return (
                self._event(
                    ThreadStatusUpdatedEvent,
                    event.turn_id,
                    "thread.status.updated",
                    provider_payload,
                    status=str(event.payload.get("status") or ""),
                ),
            )
        if event.semantic_name == "account.rate_limits.updated":
            return (
                self._event(
                    RateLimitsUpdatedEvent,
                    event.turn_id,
                    "rate_limits.updated",
                    provider_payload,
                    rate_limits=dict(event.payload.get("rate_limits") or {}),
                ),
            )
        if event.semantic_name == "skills.changed":
            return (
                self._event(
                    SkillsUpdatedEvent,
                    event.turn_id,
                    "skills.updated",
                    provider_payload,
                    version=str(event.payload.get("version") or ""),
                    skills=tuple(str(skill) for skill in event.payload.get("skills") or ()),
                ),
            )
        if event.semantic_name == "thread.diff.updated":
            return (
                self._event(
                    ThreadDiffUpdatedEvent,
                    event.turn_id,
                    "thread.diff.updated",
                    provider_payload,
                    diff=str(event.payload.get("diff") or ""),
                ),
            )
        if event.semantic_name == "turn.completed":
            return (
                self._event(
                    TurnCompletedEvent,
                    event.turn_id,
                    "turn.completed",
                    provider_payload,
                    final_text=event.final_text,
                    usage=event.usage,
                ),
            )
        if event.semantic_name == "turn.interrupted":
            return (self._event(TurnInterruptedEvent, event.turn_id, "turn.interrupted", provider_payload, message=event.message),)
        if event.semantic_name == "turn.failed":
            return (self._event(TurnFailedEvent, event.turn_id, "turn.failed", provider_payload, message=event.message),)
        if event.policy == "ignore":
            return ()
        return (
            self._event(
                BackendNoticeEvent,
                event.turn_id,
                "backend.notice",
                provider_payload,
                level=event.level,  # type: ignore[arg-type]
                message=event.message or str(event.payload.get("title") or ""),
            ),
        )

    def _event(
        self,
        event_cls: type[RuntimeEvent],
        turn_id: str,
        event_type: str,
        provider_payload: dict[str, Any],
        **kwargs: Any,
    ) -> RuntimeEvent:
        return event_cls(
            backend=self.backend,  # type: ignore[arg-type]
            session_id=self.session_id,
            turn_id=turn_id,
            event_type=event_type,
            provider_payload=provider_payload,
            **kwargs,
        )
