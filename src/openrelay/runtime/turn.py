from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.core import ActiveRun, AppConfig, IncomingMessage, SessionRecord
from openrelay.feishu import FeishuMessenger, FeishuStreamingSession, FeishuTypingManager
from openrelay.observability import MessageTraceContext, MessageTraceRecorder
from openrelay.presentation.live_turn import LiveTurnPresenter
from openrelay.session import RelaySessionBinding

from .replying import ReplyRoute


class TurnSessionUX(Protocol):
    def format_cwd(self, cwd: str, session: SessionRecord | None = None) -> str: ...
    def label_session_if_needed(self, session: SessionRecord, message_summary: str) -> SessionRecord: ...
    def shorten(self, text: object, max_length: int = 96) -> str: ...


class TurnCoordinator(Protocol):
    def start_run(self, execution_key: str, run: ActiveRun) -> None: ...
    def finish_run(self, execution_key: str) -> None: ...


class TurnStateStore(Protocol):
    def save_session(self, session: SessionRecord) -> SessionRecord: ...
    def append_message(self, session_id: str, role: str, content: str) -> None: ...


class TurnBindingStore(Protocol):
    def save(self, binding: RelaySessionBinding) -> None: ...
    def get(self, relay_session_id: str) -> RelaySessionBinding | None: ...


class TurnReplyFinalHook(Protocol):
    async def __call__(
        self,
        message: IncomingMessage,
        text: str,
        streaming: FeishuStreamingSession | None,
        live_state: dict[str, Any] | None = None,
        trace_context: MessageTraceContext | None = None,
    ) -> None: ...


@dataclass(slots=True)
class TurnRuntimeContext:
    config: AppConfig
    store: TurnStateStore
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
    reply_final: TurnReplyFinalHook
    trace_recorder: MessageTraceRecorder | None = None
    live_turn_presenter: LiveTurnPresenter | None = None
    binding_store: TurnBindingStore | None = None
    runtime_service: AgentRuntimeService | None = None
