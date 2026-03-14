from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openrelay.models import IncomingMessage


@dataclass(slots=True)
class ParsedWebhook:
    type: str
    challenge: str = ""
    status_code: int = 200
    body: dict[str, Any] | None = None
    message: IncomingMessage | None = None


@dataclass(slots=True)
class SentMessageRef:
    message_id: str = ""
    root_id: str = ""
    thread_id: str = ""
    parent_id: str = ""
    upper_message_id: str = ""

    def alias_ids(self) -> tuple[str, ...]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in [
            self.message_id,
            self.root_id,
            self.thread_id,
            self.parent_id,
            self.upper_message_id,
        ]:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return tuple(ordered)
