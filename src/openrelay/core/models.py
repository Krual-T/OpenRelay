from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable



def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class IncomingMessage:
    event_id: str
    message_id: str
    chat_id: str
    chat_type: str
    sender_open_id: str
    trace_id: str = ""
    source_kind: str = "message"
    root_id: str = ""
    thread_id: str = ""
    parent_id: str = ""
    reply_to_message_id: str = ""
    session_key: str = ""
    session_owner_open_id: str = ""
    text: str = ""
    remote_image_keys: tuple[str, ...] = ()
    local_image_paths: tuple[str, ...] = ()
    actionable: bool = False


@dataclass(slots=True)
class SessionRecord:
    session_id: str
    base_key: str
    backend: str
    cwd: str
    label: str = ""
    model_override: str = ""
    safety_mode: str = "workspace-write"
    native_session_id: str = ""
    release_channel: str = "main"
    last_usage: dict[str, object] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class SessionSummary:
    session_id: str
    base_key: str
    backend: str
    label: str
    cwd: str
    native_session_id: str
    updated_at: str
    active: bool
    release_channel: str = "main"
    first_user_message: str = ""
    last_assistant_message: str = ""
    message_count: int = 0


@dataclass(slots=True)
class BackendReply:
    text: str
    native_session_id: str = ""
    model: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ActiveRun:
    started_at: str
    description: str
    cancel: Callable[[str], Awaitable[None]]
    try_handle_input: Callable[["IncomingMessage"], Awaitable[bool]] | None = None
