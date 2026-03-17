from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from openrelay.agent_runtime import PlanStep, ToolState, UsageSnapshot

from .event_registry import EventPolicy, EventRoute


@dataclass(slots=True)
class CodexTerminalState:
    closed: bool = False
    terminal_kind: str = ""
    source_route: str = ""
    source_method: str = ""


@dataclass(frozen=True, slots=True)
class CodexRawEventEnvelope:
    method: str
    route: EventRoute
    params: dict[str, Any]
    thread_id: str
    turn_id: str
    item_id: str


@dataclass(frozen=True, slots=True)
class CodexSemanticEvent:
    semantic_name: str
    policy: EventPolicy
    source_method: str
    source_route: EventRoute
    thread_id: str
    turn_id: str
    item_id: str = ""
    dedupe_key: str = ""
    terminal_kind: str = ""
    text: str = ""
    message: str = ""
    explanation: str = ""
    steps: tuple[PlanStep, ...] = ()
    tool: ToolState | None = None
    tool_id: str = ""
    detail: str = ""
    usage: UsageSnapshot | None = None
    final_text: str = ""
    approval_id: str = ""
    level: str = "info"
    payload: dict[str, Any] = field(default_factory=dict)

