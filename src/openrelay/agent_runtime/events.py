from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from openrelay.core import utc_now

from .models import (
    ApprovalRequest,
    BackendKind,
    TerminalInteraction,
    PlanStep,
    ToolState,
    UsageSnapshot,
)


@dataclass(slots=True, frozen=True)
class RuntimeEvent:
    backend: BackendKind
    session_id: str
    turn_id: str
    event_type: str
    created_at: str = field(default_factory=utc_now)
    provider_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class SessionStartedEvent(RuntimeEvent):
    native_session_id: str = ""
    title: str = ""


@dataclass(slots=True, frozen=True)
class TurnStartedEvent(RuntimeEvent):
    pass


@dataclass(slots=True, frozen=True)
class AssistantDeltaEvent(RuntimeEvent):
    delta: str = ""


@dataclass(slots=True, frozen=True)
class AssistantCompletedEvent(RuntimeEvent):
    text: str = ""


@dataclass(slots=True, frozen=True)
class ReasoningDeltaEvent(RuntimeEvent):
    text: str = ""


@dataclass(slots=True, frozen=True)
class PlanUpdatedEvent(RuntimeEvent):
    steps: tuple[PlanStep, ...] = ()
    explanation: str = ""


@dataclass(slots=True, frozen=True)
class ToolStartedEvent(RuntimeEvent):
    tool: ToolState = field(default_factory=lambda: ToolState("", "custom", "", "pending"))


@dataclass(slots=True, frozen=True)
class ToolProgressEvent(RuntimeEvent):
    tool_id: str = ""
    detail: str = ""


@dataclass(slots=True, frozen=True)
class ToolCompletedEvent(RuntimeEvent):
    tool: ToolState = field(default_factory=lambda: ToolState("", "custom", "", "completed"))


@dataclass(slots=True, frozen=True)
class ApprovalRequestedEvent(RuntimeEvent):
    request: ApprovalRequest = field(
        default_factory=lambda: ApprovalRequest("", "", "", "custom", "", "")
    )


@dataclass(slots=True, frozen=True)
class ApprovalResolvedEvent(RuntimeEvent):
    approval_id: str = ""


@dataclass(slots=True, frozen=True)
class UsageUpdatedEvent(RuntimeEvent):
    usage: UsageSnapshot = field(default_factory=UsageSnapshot)


@dataclass(slots=True, frozen=True)
class ThreadStatusUpdatedEvent(RuntimeEvent):
    status: str = ""


@dataclass(slots=True, frozen=True)
class RateLimitsUpdatedEvent(RuntimeEvent):
    rate_limits: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class SkillsUpdatedEvent(RuntimeEvent):
    version: str = ""
    skills: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class ThreadDiffUpdatedEvent(RuntimeEvent):
    diff_id: str = ""


@dataclass(slots=True, frozen=True)
class TerminalInteractionEvent(RuntimeEvent):
    interaction: TerminalInteraction = field(default_factory=TerminalInteraction)


@dataclass(slots=True, frozen=True)
class TurnCompletedEvent(RuntimeEvent):
    final_text: str = ""
    usage: UsageSnapshot | None = None


@dataclass(slots=True, frozen=True)
class TurnFailedEvent(RuntimeEvent):
    message: str = ""


@dataclass(slots=True, frozen=True)
class TurnInterruptedEvent(RuntimeEvent):
    message: str = ""


@dataclass(slots=True, frozen=True)
class BackendNoticeEvent(RuntimeEvent):
    level: Literal["info", "warning", "error"] = "info"
    message: str = ""
