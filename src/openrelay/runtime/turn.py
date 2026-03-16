from __future__ import annotations

import asyncio
import copy
import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from openrelay.agent_runtime import (
    ApprovalRequestedEvent,
    AssistantDeltaEvent,
    PlanUpdatedEvent,
    ReasoningDeltaEvent,
    RuntimeEvent,
    SessionStartedEvent,
    ToolCompletedEvent,
    ToolStartedEvent,
    TurnCompletedEvent,
    TurnInput,
)
from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.core import ActiveRun, AppConfig, BackendReply, IncomingMessage, SessionRecord, utc_now
from openrelay.feishu import (
    FeishuMessenger,
    FeishuStreamingSession,
    FeishuTypingManager,
    STREAMING_ROLLOVER_NOTICE,
    build_streaming_content,
)
from openrelay.presentation.live_turn import LiveTurnPresenter
from openrelay.session import RelaySessionBinding, SessionBindingStore
from openrelay.storage import StateStore

from .interactions import RunInteractionController
from .live import apply_live_progress
from .replying import ReplyRoute


LOGGER = logging.getLogger("openrelay.runtime")


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
        self.session = session
        self.cancel_event = asyncio.Event()
        self.interaction_controller: RunInteractionController | None = None
        self.typing_state: dict[str, Any] | None = None
        self.streaming: FeishuStreamingSession | None = None
        self.streaming_broken = False
        self.last_live_text = ""
        self.spinner_task: asyncio.Task[None] | None = None
        self.streaming_update_event = asyncio.Event()
        self.pending_streaming_states: deque[dict[str, Any]] = deque()
        self.presenter = runtime.live_turn_presenter or LiveTurnPresenter()
        self.live_state = self.presenter.create_initial_snapshot(session, runtime.session_ux.format_cwd)

    async def run(self, message_summary: str, backend_prompt: str) -> None:
        try:
            await self.prepare(message_summary)
            self.build_interaction_controller()
            self.runtime.execution_coordinator.start_run(self.execution_key, self.activate_run(message_summary))
            if not self._should_use_agent_runtime():
                raise RuntimeError(f"Unsupported backend: {self.session.backend}")
            reply = await self.run_with_agent_runtime(backend_prompt)
            await self.save_reply(reply)
            await self.reply_final(reply.text or "(empty reply)")
        except Exception as exc:
            if "interrupted by /stop" in str(exc).lower() or "interrupted" in str(exc).lower():
                await self.reply_final("已停止当前回复。")
            else:
                await self.reply_final(f"处理失败：{exc}")
        finally:
            self.runtime.execution_coordinator.finish_run(self.execution_key)
            await self.finalize()

    async def prepare(self, message_summary: str) -> None:
        self.session = self.runtime.session_ux.label_session_if_needed(self.session, message_summary)
        self.runtime.store.save_session(self.session)
        self.runtime.store.append_message(self.session.session_id, "user", message_summary)
        await self._start_typing()
        await self._start_streaming_if_needed()

    async def persist_native_thread_id(self, thread_id: str) -> None:
        normalized = str(thread_id or "").strip()
        if not normalized or self.session.native_session_id == normalized:
            return
        self.session.native_session_id = normalized
        self.runtime.store.save_session(self.session)
        LOGGER.info(
            "persisted native thread early event_id=%s message_id=%s session_id=%s native_session_id=%s",
            self.message.event_id,
            self.message.message_id,
            self.session.session_id,
            normalized,
        )

    async def cancel(self, _reason: str) -> None:
        self.cancel_event.set()
        if self.interaction_controller is not None:
            await self.interaction_controller.shutdown()

    def build_interaction_controller(self) -> RunInteractionController:
        self.interaction_controller = RunInteractionController(
            self.runtime.messenger,
            chat_id=self.message.chat_id,
            root_id=self.runtime.root_id_for_message(self.message),
            action_context=self.runtime.build_card_action_context(self.message, self.session.base_key),
            reply_target_getter=self.reply_target_message_id,
            emit_progress=self.on_progress,
            send_text=lambda text: self.runtime.messenger.send_text(
                self.message.chat_id,
                text,
                reply_to_message_id=self.reply_target_message_id(),
                root_id=self.runtime.root_id_for_message(self.message),
            ),
            cancel_event=self.cancel_event,
        )
        return self.interaction_controller

    def activate_run(self, message_summary: str) -> ActiveRun:
        return ActiveRun(
            started_at=utc_now(),
            description=self.runtime.session_ux.shorten(message_summary, 72),
            cancel=self.cancel,
            try_handle_input=self.interaction_controller.try_handle_message if self.interaction_controller is not None else None,
        )

    async def on_partial_text(self, partial_text: str) -> None:
        if not partial_text.strip():
            return
        self.live_state["heading"] = "Generating reply"
        self.live_state["status"] = "Streaming output"
        self.live_state["partial_text"] = partial_text
        self._request_streaming_update()

    async def on_progress(self, event: dict[str, Any]) -> None:
        apply_live_progress(self.live_state, event)
        self._request_streaming_update()

    async def run_with_agent_runtime(self, backend_prompt: str) -> BackendReply:
        runtime_service = self.runtime.runtime_service
        binding_store = self.runtime.binding_store
        if runtime_service is None or binding_store is None:
            raise RuntimeError("agent runtime service is unavailable")
        binding = self._ensure_binding(binding_store)
        await self.on_progress({"type": "run.started"})

        async def handle_runtime_event(event: RuntimeEvent) -> None:
            if event.session_id != self.session.session_id:
                return
            await self._handle_runtime_event(binding, event)

        runtime_service.event_hub.subscribe(handle_runtime_event)
        try:
            state = await runtime_service.run_turn(
                binding,
                TurnInput(
                    text=backend_prompt,
                    local_image_paths=self.message.local_image_paths,
                    cwd=self.session.cwd,
                    model=self.session.model_override or None,
                    safety_mode=self.session.safety_mode,
                ),
            )
        finally:
            runtime_service.event_hub.unsubscribe(handle_runtime_event)

        binding = binding_store.get(self.session.session_id) or binding
        usage = None
        if state.usage is not None:
            usage = {
                "input_tokens": state.usage.input_tokens,
                "cached_input_tokens": state.usage.cached_input_tokens,
                "output_tokens": state.usage.output_tokens,
                "reasoning_output_tokens": state.usage.reasoning_output_tokens,
                "total_tokens": state.usage.total_tokens,
                "model_context_window": state.usage.context_window,
            }
        return BackendReply(
            text=state.assistant_text,
            native_session_id=binding.native_session_id,
            metadata={"usage": usage or {}},
        )

    async def _handle_runtime_event(
        self,
        binding: RelaySessionBinding,
        event: RuntimeEvent,
    ) -> None:
        runtime_service = self.runtime.runtime_service
        if runtime_service is None:
            return
        state = runtime_service.turn_registry.read(event.session_id, event.turn_id) if event.turn_id else None
        if isinstance(event, SessionStartedEvent):
            await self.persist_native_thread_id(event.native_session_id)
            self.live_state["native_session_id"] = event.native_session_id
        if state is not None:
            self.live_state = self.presenter.build_snapshot(
                state,
                previous=self.live_state,
                session=self.session,
                format_cwd=self.runtime.session_ux.format_cwd,
            )
        if isinstance(event, AssistantDeltaEvent) and state is not None:
            self.last_live_text = ""
        if isinstance(event, ApprovalRequestedEvent):
            if self.interaction_controller is None:
                raise RuntimeError("interaction controller is unavailable for approval")
            self._request_streaming_update()
            await runtime_service.resolve_approval(
                binding,
                event.request,
                await self.interaction_controller.request_approval(event.request),
            )
            apply_live_progress(
                self.live_state,
                {
                    "type": "interaction.resolved",
                    "interaction": {
                        "id": event.request.approval_id,
                        "detail": "Approval resolved",
                    },
                },
            )
        self._request_streaming_update()

    def _ensure_binding(self, binding_store: SessionBindingStore) -> RelaySessionBinding:
        existing = binding_store.get(self.session.session_id)
        if existing is not None:
            return existing
        binding = RelaySessionBinding(
            relay_session_id=self.session.session_id,
            backend=self.session.backend,  # type: ignore[arg-type]
            native_session_id=self.session.native_session_id,
            cwd=self.session.cwd,
            model=self.session.model_override,
            safety_mode=self.session.safety_mode,
            feishu_chat_id=self.message.chat_id,
            feishu_thread_id=self.message.thread_id or self.message.root_id or "",
        )
        binding_store.save(binding)
        return binding

    def _should_use_agent_runtime(self) -> bool:
        runtime_service = self.runtime.runtime_service
        return runtime_service is not None and self.session.backend in runtime_service.backends

    def reply_target_message_id(self) -> str:
        if self.streaming is not None and self.streaming.has_started() and self.streaming.message_id():
            return self.streaming.message_id()
        return self.message.reply_to_message_id or ("" if self.runtime.is_card_action_message(self.message) else self.message.message_id)

    async def _start_streaming_session(self, route: ReplyRoute | None = None) -> FeishuStreamingSession:
        current_route = route or self.runtime.streaming_route_for_message(self.message)
        session = self.runtime.streaming_session_factory(self.runtime.messenger)
        await session.start(
            self.message.chat_id,
            reply_to_message_id=current_route.reply_to_message_id,
            root_id=current_route.root_id,
        )
        self.runtime.remember_outbound_aliases(
            self.message,
            self.runtime.build_session_key(self.message),
            [session.message_alias_ids()],
        )
        self.streaming = session
        return session

    async def _roll_over_streaming(self, snapshot: dict[str, Any]) -> None:
        previous_streaming = self.streaming
        if previous_streaming is not None and previous_streaming.needs_rollover():
            await previous_streaming.freeze(snapshot, notice_text=STREAMING_ROLLOVER_NOTICE)
        self.streaming = None
        next_streaming = await self._start_streaming_session()
        if not next_streaming.is_active():
            return
        await next_streaming.update(snapshot)

    async def save_reply(self, reply: BackendReply) -> SessionRecord:
        updated = SessionRecord(
            session_id=self.session.session_id,
            base_key=self.session.base_key,
            backend=self.session.backend,
            cwd=self.session.cwd,
            label=self.session.label,
            model_override=self.session.model_override,
            safety_mode=self.session.safety_mode,
            native_session_id=reply.native_session_id or self.session.native_session_id,
            release_channel=self.session.release_channel,
            last_usage=reply.metadata.get("usage", {}) if isinstance(reply.metadata, dict) else {},
            created_at=self.session.created_at,
        )
        updated = self.runtime.store.save_session(updated)
        LOGGER.info(
            "backend turn saved session event_id=%s message_id=%s session_id=%s native_session_id=%s backend=%s",
            self.message.event_id,
            self.message.message_id,
            updated.session_id,
            updated.native_session_id,
            updated.backend,
        )
        self.runtime.store.append_message(updated.session_id, "assistant", reply.text)
        self.session = updated
        return updated

    async def reply_final(self, text: str) -> None:
        self._stop_spinner_task()
        await self.runtime.reply_final(self.message, text, self.streaming, self.live_state)

    async def finalize(self) -> None:
        self._stop_spinner_task()
        if self.interaction_controller is not None:
            await self.interaction_controller.shutdown()
        if self.typing_state is not None:
            try:
                await self.runtime.typing_manager.remove(self.typing_state)
            except Exception:
                LOGGER.exception("typing stop failed for message_id=%s", self.message.message_id)

    async def _start_typing(self) -> None:
        if not self.message.message_id or self.runtime.config.feishu.stream_mode == "off":
            return
        try:
            self.typing_state = await self.runtime.typing_manager.add(self.message.message_id)
        except Exception:
            LOGGER.exception("typing start failed for message_id=%s", self.message.message_id)

    async def _start_streaming_if_needed(self) -> None:
        if self.runtime.config.feishu.stream_mode != "card":
            return
        if self.streaming is None:
            await self._start_streaming_session()
        self.pending_streaming_states.append(copy.deepcopy(self.live_state))
        await self._update_streaming(self.pending_streaming_states.popleft())
        self.spinner_task = asyncio.create_task(self._spinner_loop())

    def _stop_spinner_task(self) -> None:
        if self.spinner_task is None:
            return
        self.spinner_task.cancel()
        self.spinner_task = None

    def _request_streaming_update(self) -> None:
        if self.runtime.config.feishu.stream_mode != "card" or self.streaming_broken:
            return
        self.pending_streaming_states.append(copy.deepcopy(self.live_state))
        self.streaming_update_event.set()

    async def _update_streaming(self, snapshot: dict[str, Any]) -> None:
        if self.runtime.config.feishu.stream_mode != "card" or self.streaming_broken:
            return
        live_text = build_streaming_content(snapshot)
        if not live_text or live_text == self.last_live_text:
            return
        try:
            if self.streaming is None:
                await self._start_streaming_session()
            if not self.streaming.is_active():
                if self.streaming.needs_rollover():
                    await self._roll_over_streaming(snapshot)
                    return
                self._stop_spinner_task()
                return
            await self.streaming.update(snapshot)
            if not self.streaming.is_active():
                if self.streaming.needs_rollover():
                    await self._roll_over_streaming(snapshot)
                    return
                self._stop_spinner_task()
            self.last_live_text = live_text
        except Exception:
            has_started = self.streaming.has_started() if self.streaming is not None else False
            self.streaming_broken = True
            if not has_started:
                self.streaming = None
            self._stop_spinner_task()
            LOGGER.exception("streaming update failed for execution_key=%s", self.execution_key)

    async def _spinner_loop(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self.streaming_update_event.wait(), timeout=1.0)
                self.streaming_update_event.clear()
            except asyncio.TimeoutError:
                self.live_state["spinner_frame"] = (int(self.live_state.get("spinner_frame", 0) or 0) + 1) % 3
                self.pending_streaming_states.append(copy.deepcopy(self.live_state))
            try:
                while self.pending_streaming_states:
                    snapshot = self.pending_streaming_states.popleft()
                    await self._update_streaming(snapshot)
            except Exception:
                self._stop_spinner_task()
                LOGGER.exception("streaming tick failed for execution_key=%s", self.execution_key)
                return
