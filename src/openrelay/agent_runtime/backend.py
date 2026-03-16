from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .events import RuntimeEvent
from .models import (
    ApprovalDecision,
    ApprovalRequest,
    BackendKind,
    SessionLocator,
    SessionSummary,
    SessionTranscript,
    TurnInput,
)


@dataclass(slots=True, frozen=True)
class BackendCapabilities:
    supports_session_list: bool = False
    supports_session_read: bool = False
    supports_compact: bool = False
    supports_output_schema: bool = False
    supports_plan_updates: bool = False
    supports_reasoning_stream: bool = False
    supports_file_change_approval: bool = False
    supports_command_approval: bool = False


@dataclass(slots=True, frozen=True)
class StartSessionRequest:
    cwd: str
    model: str | None = None
    safety_mode: str = "workspace-write"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ListSessionsRequest:
    limit: int = 20
    cursor: str = ""
    cwd: str | None = None


class RuntimeEventSink(Protocol):
    async def publish(self, event: RuntimeEvent) -> None:
        raise NotImplementedError


class RunningTurnHandle(Protocol):
    session_id: str
    turn_id: str
    backend: BackendKind

    async def wait(self) -> None:
        raise NotImplementedError


class AgentBackend(Protocol):
    def name(self) -> BackendKind:
        raise NotImplementedError

    def capabilities(self) -> BackendCapabilities:
        raise NotImplementedError

    async def start_session(self, request: StartSessionRequest) -> SessionSummary:
        raise NotImplementedError

    async def resume_session(self, locator: SessionLocator) -> SessionSummary:
        raise NotImplementedError

    async def list_sessions(self, request: ListSessionsRequest) -> tuple[list[SessionSummary], str]:
        raise NotImplementedError

    async def read_session(self, locator: SessionLocator) -> SessionTranscript:
        raise NotImplementedError

    async def start_turn(
        self,
        locator: SessionLocator,
        turn_input: TurnInput,
        sink: RuntimeEventSink,
    ) -> RunningTurnHandle:
        raise NotImplementedError

    async def interrupt_turn(self, locator: SessionLocator, turn_id: str) -> None:
        raise NotImplementedError

    async def resolve_approval(
        self,
        locator: SessionLocator,
        approval: ApprovalDecision,
        request: ApprovalRequest,
    ) -> None:
        raise NotImplementedError

    async def compact_session(self, locator: SessionLocator) -> dict[str, Any]:
        raise NotImplementedError

    async def shutdown(self) -> None:
        raise NotImplementedError
