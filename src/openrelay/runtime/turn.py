from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.core import ActiveRun, AppConfig, IncomingMessage, SessionRecord
from openrelay.feishu import FeishuMessenger, FeishuStreamingSession, FeishuTypingManager
from openrelay.presentation.live_turn import LiveTurnPresenter
from openrelay.session import SessionBindingStore
from openrelay.storage import StateStore

from .replying import ReplyRoute
from .turn_application import TurnApplicationService
from .turn_run_controller import TurnRunController
from .turn_runtime_event_bridge import TurnRuntimeEventBridge


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
    reply_final: Callable[[IncomingMessage, str, FeishuStreamingSession | None, dict[str, Any] | None], Awaitable[None]]
    live_turn_presenter: LiveTurnPresenter | None = None
    binding_store: SessionBindingStore | None = None
    runtime_service: AgentRuntimeService | None = None


class BackendTurnSession:
    def __init__(self, runtime: TurnRuntimeContext, message: IncomingMessage, execution_key: str, session: SessionRecord):
        self.runtime = runtime
        self.message = message
        self.execution_key = execution_key
        self.presenter = runtime.live_turn_presenter or LiveTurnPresenter()
        self.controller = TurnRunController(runtime, message, execution_key, self.presenter)
        self.controller.initialize(session)
        self.event_bridge = TurnRuntimeEventBridge(runtime, self.controller, self.presenter)
        self.application = TurnApplicationService(runtime, message, execution_key, self.controller, self.event_bridge)

    async def run(self, message_summary: str, backend_prompt: str) -> None:
        await self.application.run(message_summary, backend_prompt)

    async def cancel(self, reason: str) -> None:
        await self.controller.cancel(reason)

    async def prepare(self, message_summary: str) -> None:
        await self.controller.prepare(message_summary)

    async def persist_native_thread_id(self, thread_id: str) -> None:
        await self.controller.persist_native_thread_id(thread_id)

    def build_interaction_controller(self) -> Any:
        return self.controller.build_interaction_controller()

    def activate_run(self, message_summary: str) -> ActiveRun:
        return self.controller.activate_run(message_summary)

    def reply_target_message_id(self) -> str:
        return self.controller.reply_target_message_id()

    def _request_streaming_update(self) -> None:
        self.controller.request_streaming_update()

    @property
    def session(self) -> SessionRecord:
        return self.controller.state.session

    @session.setter
    def session(self, value: SessionRecord) -> None:
        self.controller.state.session = value

    @property
    def live_state(self) -> dict[str, Any]:
        return self.controller.state.live_state

    @live_state.setter
    def live_state(self, value: dict[str, Any]) -> None:
        self.controller.state.live_state = value

    @property
    def streaming(self) -> FeishuStreamingSession | None:
        return self.controller.state.streaming

    @streaming.setter
    def streaming(self, value: FeishuStreamingSession | None) -> None:
        self.controller.state.streaming = value

    @property
    def pending_streaming_states(self) -> Any:
        return self.controller.state.pending_streaming_states

    @property
    def spinner_task(self) -> Any:
        return self.controller.state.spinner_task

    @spinner_task.setter
    def spinner_task(self, value: Any) -> None:
        self.controller.state.spinner_task = value

    @property
    def cancel_event(self) -> Any:
        return self.controller.state.cancel_event

    @property
    def streaming_update_event(self) -> Any:
        return self.controller.state.streaming_update_event
