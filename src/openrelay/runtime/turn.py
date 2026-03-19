from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.core import ActiveRun, AppConfig, IncomingMessage, SessionRecord
from openrelay.feishu import FeishuMessenger, FeishuStreamingSession, FeishuTypingManager
from openrelay.observability import MessageTraceRecorder
from openrelay.presentation.live_turn import LiveTurnPresenter
from openrelay.session import SessionBindingStore
from openrelay.storage import StateStore

from .replying import ReplyRoute


class TurnSessionUX(Protocol):
    def format_cwd(self, cwd: str, session: SessionRecord | None = None) -> str: ...
    def label_session_if_needed(self, session: SessionRecord, message_summary: str) -> SessionRecord: ...
    def shorten(self, text: object, max_length: int = 96) -> str: ...


class TurnCoordinator(Protocol):
    def start_run(self, execution_key: str, run: ActiveRun) -> None: ...
    def finish_run(self, execution_key: str) -> None: ...


@dataclass(slots=True)
class TurnRuntimeContext:
    config: AppConfig
    store: StateStore
    messenger: FeishuMessenger
    typing_manager: FeishuTypingManager
    session_ux: TurnSessionUX
    streaming_session_factory: Callable[[FeishuMessenger], FeishuStreamingSession]
    execution_coordinator: TurnCoordinator
    build_card_action_context: Callable[[IncomingMessage, str], dict[str, str]]
    streaming_route_for_message: Callable[[IncomingMessage], ReplyRoute]
    root_id_for_message: Callable[[IncomingMessage], str]
    is_card_action_message: Callable[[IncomingMessage], bool]
    build_session_key: Callable[[IncomingMessage], str]
    remember_outbound_aliases: Callable[[IncomingMessage, str, list[tuple[str, ...]]], None]
    reply_final: Callable[..., Awaitable[None]]
    trace_recorder: MessageTraceRecorder | None = None
    live_turn_presenter: LiveTurnPresenter | None = None
    binding_store: SessionBindingStore | None = None
    runtime_service: AgentRuntimeService | None = None
