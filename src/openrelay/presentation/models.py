from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class TurnHistoryItem:
    item_type: str
    state: str = ""
    title: str = ""
    detail: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_legacy_dict(self) -> dict[str, Any]:
        data = {
            "type": self.item_type,
            "state": self.state,
            "title": self.title,
            "detail": self.detail,
        }
        data.update(self.payload)
        return data


@dataclass(slots=True, frozen=True)
class TurnViewSnapshot:
    session_id: str
    native_session_id: str
    cwd: str
    heading: str
    status: str
    current_command: str
    last_command: dict[str, Any] | None
    last_reasoning: str
    reasoning_text: str
    reasoning_started_at: str
    reasoning_elapsed_ms: int
    partial_text: str
    committed_partial_text: str
    spinner_frame: int
    started_at: str
    history: tuple[dict[str, Any], ...] = ()
    history_items: tuple[TurnHistoryItem, ...] = ()
    transcript_items: tuple[TurnHistoryItem, ...] = ()
    plan_history_items: tuple[TurnHistoryItem, ...] = ()
    commands: tuple[dict[str, Any], ...] = ()

    def to_legacy_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "native_session_id": self.native_session_id,
            "cwd": self.cwd,
            "history": [dict(item) for item in self.history],
            "history_items": [item.to_legacy_dict() for item in self.history_items],
            "plan_history_items": [item.to_legacy_dict() for item in self.plan_history_items],
            "transcript_items": [item.to_legacy_dict() for item in self.transcript_items],
            "heading": self.heading,
            "status": self.status,
            "current_command": self.current_command,
            "last_command": dict(self.last_command) if isinstance(self.last_command, dict) else self.last_command,
            "commands": [dict(item) for item in self.commands],
            "last_reasoning": self.last_reasoning,
            "reasoning_text": self.reasoning_text,
            "reasoning_started_at": self.reasoning_started_at,
            "reasoning_elapsed_ms": self.reasoning_elapsed_ms,
            "partial_text": self.partial_text,
            "committed_partial_text": self.committed_partial_text,
            "spinner_frame": self.spinner_frame,
            "started_at": self.started_at,
        }
