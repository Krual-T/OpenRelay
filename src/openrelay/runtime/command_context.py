from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

from openrelay.core import IncomingMessage, SessionRecord
from openrelay.session import SessionSortMode

ReplyHook = Callable[..., Awaitable[None]]
SendHelpHook = Callable[[IncomingMessage, str, SessionRecord, list[str]], Awaitable[None]]
SendPanelHook = Callable[[IncomingMessage, str, SessionRecord, "PanelCommandArgs"], Awaitable[None]]
SendSessionListHook = Callable[[IncomingMessage, str, SessionRecord, int, SessionSortMode], Awaitable[None]]
StopHook = Callable[[IncomingMessage, str], Awaitable[None]]
ScheduleRestartHook = Callable[[], None]
IsAdminHook = Callable[[str], bool]
AvailableBackendsHook = Callable[[], list[str]]
CancelActiveRunHook = Callable[[SessionRecord, str], Awaitable[bool]]

PanelView = Literal["home", "sessions", "workspace", "commands", "status"]


@dataclass(slots=True)
class RuntimeCommandHooks:
    reply: ReplyHook
    send_help: SendHelpHook
    send_panel: SendPanelHook
    send_session_list: SendSessionListHook
    stop: StopHook
    schedule_restart: ScheduleRestartHook
    is_admin: IsAdminHook
    available_backend_names: AvailableBackendsHook
    cancel_active_run_for_session: CancelActiveRunHook


@dataclass(slots=True)
class ResumeCommandArgs:
    target: str
    page: int
    sort_mode: SessionSortMode


@dataclass(slots=True)
class PanelCommandArgs:
    view: PanelView
    page: int
    sort_mode: SessionSortMode
    target_path: str = ""
    query: str = ""
    show_hidden: bool = False


@dataclass(slots=True)
class PagingCommandArgs:
    target: str
    page: int
    sort_mode: SessionSortMode
    target_path: str = ""
    query: str = ""
    show_hidden: bool = False


@dataclass(slots=True)
class RuntimeSessionSummary:
    session_id: str
    preview: str
    cwd: str
    updated_at: str
    status: str
    name: str


@dataclass(slots=True)
class RuntimeTranscriptMessage:
    role: str
    text: str


@dataclass(slots=True)
class RuntimeSessionDetails:
    session_id: str
    preview: str
    cwd: str
    updated_at: str
    status: str
    name: str
    messages: tuple[RuntimeTranscriptMessage, ...]


@dataclass(slots=True)
class ParsedCommand:
    name: str
    arg_text: str
    raw_text: str


@dataclass(slots=True)
class CommandContext:
    message: IncomingMessage
    session_key: str
    session: SessionRecord
    command: ParsedCommand
