from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable


INTERACTION_COMMAND_PREFIX = "/__openrelay_interaction__"


def build_interaction_command(interaction_id: str, action: str) -> str:
    return f"{INTERACTION_COMMAND_PREFIX} {interaction_id} {action}"


@dataclass(slots=True)
class InteractionResolution:
    response: dict[str, Any]
    label: str
    state: str = "completed"
    detail: str = ""


@dataclass(slots=True)
class PendingInteraction:
    interaction_id: str
    kind: str
    title: str
    detail: str
    prompt_text: str
    future: asyncio.Future[InteractionResolution]
    abort_resolution: InteractionResolution
    text_handler: Callable[[str], InteractionResolution | None] | None = None
    command_resolutions: dict[str, InteractionResolution] | None = None
