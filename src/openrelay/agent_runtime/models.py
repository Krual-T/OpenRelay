from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from openrelay.core import utc_now


BackendKind: TypeAlias = Literal["codex", "claude"]
ApprovalKind: TypeAlias = Literal["command", "file_change", "permissions", "user_input", "custom"]
ApprovalDecisionKind: TypeAlias = Literal["accept", "accept_for_session", "decline", "cancel", "custom"]
ToolKind: TypeAlias = Literal["command", "file_change", "web_search", "mcp", "review", "custom"]
ToolStatus: TypeAlias = Literal["pending", "running", "completed", "failed", "declined"]
TurnStatus: TypeAlias = Literal["idle", "running", "completed", "failed", "interrupted"]
MessageRole: TypeAlias = Literal["user", "assistant", "system"]
PlanStepStatus: TypeAlias = Literal["pending", "in_progress", "completed"]


@dataclass(slots=True, frozen=True)
class SessionLocator:
    backend: BackendKind
    native_session_id: str


@dataclass(slots=True, frozen=True)
class SessionSummary:
    backend: BackendKind
    native_session_id: str
    title: str
    preview: str
    cwd: str
    updated_at: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class TranscriptMessage:
    role: MessageRole
    text: str
    created_at: str | None = None


@dataclass(slots=True, frozen=True)
class SessionTranscript:
    summary: SessionSummary
    messages: tuple[TranscriptMessage, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class TurnInput:
    text: str
    local_image_paths: tuple[str, ...] = ()
    cwd: str = ""
    model: str | None = None
    safety_mode: str = "workspace-write"
    output_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ApprovalRequest:
    approval_id: str
    session_id: str
    turn_id: str
    kind: ApprovalKind
    title: str
    description: str
    payload: dict[str, Any] = field(default_factory=dict)
    options: tuple[str, ...] = ()
    provider_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ApprovalDecision:
    decision: ApprovalDecisionKind
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ToolState:
    tool_id: str
    kind: ToolKind
    title: str
    status: ToolStatus
    preview: str = ""
    detail: str = ""
    exit_code: int | None = None
    provider_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class PlanStep:
    step: str
    status: PlanStepStatus


@dataclass(slots=True, frozen=True)
class UsageSnapshot:
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    total_tokens: int | None = None
    context_window: int | None = None


@dataclass(slots=True, frozen=True)
class BackendEventRecord:
    event_type: str
    level: Literal["info", "warning", "error"] = "info"
    title: str = ""
    detail: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True, frozen=True)
class TerminalInteraction:
    item_id: str = ""
    process_id: str = ""
    stdin: str = ""
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class LiveTurnViewModel:
    backend: BackendKind
    session_id: str
    native_session_id: str
    turn_id: str
    status: TurnStatus = "idle"
    assistant_text: str = ""
    reasoning_text: str = ""
    plan_steps: tuple[PlanStep, ...] = ()
    tools: tuple[ToolState, ...] = ()
    backend_events: tuple[BackendEventRecord, ...] = ()
    pending_approval: ApprovalRequest | None = None
    usage: UsageSnapshot | None = None
    thread_status: str = ""
    rate_limits: dict[str, Any] = field(default_factory=dict)
    skills_version: str = ""
    available_skills: tuple[str, ...] = ()
    last_diff_id: str = ""
    terminal_interactions: tuple[TerminalInteraction, ...] = ()
    error_message: str = ""
    updated_at: str = field(default_factory=utc_now)
