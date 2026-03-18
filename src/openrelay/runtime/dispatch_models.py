from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from openrelay.core import IncomingMessage, SessionRecord


DispatchKind = Literal["command", "turn", "stop", "ignored"]


@dataclass(slots=True)
class ResolvedMessageContext:
    message: IncomingMessage
    session_key: str
    session: SessionRecord
    is_top_level_control_command: bool
    is_top_level_message: bool
    control_key: str


@dataclass(slots=True)
class DispatchDecision:
    kind: DispatchKind
    resolved: ResolvedMessageContext
    execution_key: str
    command_name: str = ""
