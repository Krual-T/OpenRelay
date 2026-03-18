from __future__ import annotations

import asyncio
import copy
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from openrelay.core import ActiveRun, BackendReply, IncomingMessage, SessionRecord, utc_now
from openrelay.feishu import FeishuStreamingSession, STREAMING_ROLLOVER_NOTICE
from openrelay.feishu.renderers.live_turn_renderer import FeishuLiveTurnRenderer

from .interactions import RunInteractionController


LOGGER = logging.getLogger("openrelay.runtime")


@dataclass(slots=True)
class TurnRunState:
    session: SessionRecord
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    interaction_controller: RunInteractionController | None = None
    typing_state: dict[str, Any] | None = None
    streaming: FeishuStreamingSession | None = None
    streaming_broken: bool = False
    last_live_text: str = ""
    spinner_task: asyncio.Task[None] | None = None
    streaming_update_event: asyncio.Event = field(default_factory=asyncio.Event)
    pending_streaming_states: deque[dict[str, Any]] = field(default_factory=deque)
    live_state: dict[str, Any] = field(default_factory=dict)


class TurnRunController:
    def __init__(self, runtime: Any, message: IncomingMessage, execution_key: str, presenter: Any) -> None:
        self.runtime = runtime
        self.message = message
        self.execution_key = execution_key
        self.presenter = presenter
        self.renderer = FeishuLiveTurnRenderer()
        self.state = TurnRunState(
            session=SessionRecord(session_id="", base_key="", backend="", cwd=""),
        )

    def initialize(self, session: SessionRecord) -> None:
        self.state.session = session
        self.state.live_state = self.presenter.create_initial_snapshot(session, self.runtime.session_ux.format_cwd)

    async def prepare(self, message_summary: str) -> None:
        self.state.session = self.runtime.session_ux.label_session_if_needed(self.state.session, message_summary)
        self.runtime.store.save_session(self.state.session)
        self.runtime.store.append_message(self.state.session.session_id, "user", message_summary)
        await self._start_typing()
        await self._start_streaming_if_needed()

    async def persist_native_thread_id(self, thread_id: str) -> None:
        normalized = str(thread_id or "").strip()
        if not normalized or self.state.session.native_session_id == normalized:
            return
        self.state.session.native_session_id = normalized
        self.runtime.store.save_session(self.state.session)
        LOGGER.info(
            "persisted native thread early event_id=%s message_id=%s session_id=%s native_session_id=%s",
            self.message.event_id,
            self.message.message_id,
            self.state.session.session_id,
            normalized,
        )

    async def cancel(self, _reason: str) -> None:
        self.state.cancel_event.set()
        self.state.pending_streaming_states.clear()
        self.state.streaming_update_event.clear()
        self._stop_spinner_task()
        await self._close_streaming_for_cancel()
        if self.state.interaction_controller is not None:
            await self.state.interaction_controller.shutdown()

    def build_interaction_controller(self) -> RunInteractionController:
        self.state.interaction_controller = RunInteractionController(
            self.runtime.messenger,
            chat_id=self.message.chat_id,
            root_id=self.runtime.root_id_for_message(self.message),
            action_context=self.runtime.build_card_action_context(self.message, self.state.session.base_key),
            reply_target_getter=self.reply_target_message_id,
            send_text=lambda text: self.runtime.messenger.send_text(
                self.message.chat_id,
                text,
                reply_to_message_id=self.reply_target_message_id(),
                root_id=self.runtime.root_id_for_message(self.message),
            ),
            cancel_event=self.state.cancel_event,
        )
        return self.state.interaction_controller

    def activate_run(self, message_summary: str) -> ActiveRun:
        return ActiveRun(
            started_at=utc_now(),
            description=self.runtime.session_ux.shorten(message_summary, 72),
            cancel=self.cancel,
            try_handle_input=self.state.interaction_controller.try_handle_message if self.state.interaction_controller is not None else None,
        )

    def reply_target_message_id(self) -> str:
        streaming = self.state.streaming
        if streaming is not None and streaming.has_started() and streaming.message_id():
            return streaming.message_id()
        return self.message.reply_to_message_id or ("" if self.runtime.is_card_action_message(self.message) else self.message.message_id)

    async def start_streaming_session(self, route: Any | None = None) -> FeishuStreamingSession:
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
        self.state.streaming = session
        return session

    async def roll_over_streaming(self, snapshot: dict[str, Any]) -> None:
        previous_streaming = self.state.streaming
        if previous_streaming is not None and previous_streaming.needs_rollover():
            await previous_streaming.freeze(snapshot, notice_text=STREAMING_ROLLOVER_NOTICE)
        self.state.streaming = None
        next_streaming = await self.start_streaming_session()
        if not next_streaming.is_active():
            return
        await next_streaming.update(snapshot)

    async def reply_final(self, text: str) -> None:
        self._stop_spinner_task()
        await self.runtime.reply_final(self.message, text, self.state.streaming, self.state.live_state)

    async def finalize(self) -> None:
        self._stop_spinner_task()
        if self.state.interaction_controller is not None:
            await self.state.interaction_controller.shutdown()
        if self.state.typing_state is not None:
            try:
                await self.runtime.typing_manager.remove(self.state.typing_state)
            except Exception:
                LOGGER.exception("typing stop failed for message_id=%s", self.message.message_id)

    def request_streaming_update(self) -> None:
        if self.runtime.config.feishu.stream_mode != "card" or self.state.streaming_broken or self.state.cancel_event.is_set():
            return
        self.state.pending_streaming_states.append(copy.deepcopy(self.state.live_state))
        self.state.streaming_update_event.set()

    async def update_streaming(self, snapshot: dict[str, Any]) -> None:
        if self.runtime.config.feishu.stream_mode != "card" or self.state.streaming_broken:
            return
        live_text = self.renderer.build_streaming_content(snapshot)
        if not live_text or live_text == self.state.last_live_text:
            return
        try:
            if self.state.streaming is None:
                await self.start_streaming_session()
            if not self.state.streaming.is_active():
                if self.state.streaming.needs_rollover():
                    await self.roll_over_streaming(snapshot)
                    return
                self._stop_spinner_task()
                return
            await self.state.streaming.update(snapshot)
            if not self.state.streaming.is_active():
                if self.state.streaming.needs_rollover():
                    await self.roll_over_streaming(snapshot)
                    return
                self._stop_spinner_task()
            self.state.last_live_text = live_text
        except Exception:
            has_started = self.state.streaming.has_started() if self.state.streaming is not None else False
            self.state.streaming_broken = True
            if not has_started:
                self.state.streaming = None
            self._stop_spinner_task()
            LOGGER.exception("streaming update failed for execution_key=%s", self.execution_key)

    async def spinner_loop(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self.state.streaming_update_event.wait(), timeout=1.0)
                self.state.streaming_update_event.clear()
            except asyncio.TimeoutError:
                self.state.live_state = self.presenter.bump_spinner(self.state.live_state)
                self.state.pending_streaming_states.append(copy.deepcopy(self.state.live_state))
            try:
                while self.state.pending_streaming_states:
                    snapshot = self.state.pending_streaming_states.popleft()
                    await self.update_streaming(snapshot)
            except Exception:
                self._stop_spinner_task()
                LOGGER.exception("streaming tick failed for execution_key=%s", self.execution_key)
                return

    def start_spinner(self) -> None:
        self.state.spinner_task = asyncio.create_task(self.spinner_loop())

    def _stop_spinner_task(self) -> None:
        if self.state.spinner_task is None:
            return
        self.state.spinner_task.cancel()
        self.state.spinner_task = None

    async def _start_typing(self) -> None:
        if not self.message.message_id or self.runtime.config.feishu.stream_mode == "off":
            return
        try:
            self.state.typing_state = await self.runtime.typing_manager.add(self.message.message_id)
        except Exception:
            LOGGER.exception("typing start failed for message_id=%s", self.message.message_id)

    async def _start_streaming_if_needed(self) -> None:
        if self.runtime.config.feishu.stream_mode != "card":
            return
        if self.state.streaming is None:
            await self.start_streaming_session()
        self.state.pending_streaming_states.append(copy.deepcopy(self.state.live_state))
        await self.update_streaming(self.state.pending_streaming_states.popleft())
        self.start_spinner()

    async def _close_streaming_for_cancel(self) -> None:
        if self.runtime.config.feishu.stream_mode != "card":
            return
        if self.state.streaming is None or not self.state.streaming.has_started():
            return
        try:
            await self.state.streaming.close(self.renderer.build_final_card(self.state.live_state, fallback_text="已停止当前回复。"))
        except Exception:
            LOGGER.exception("streaming cancel close failed for execution_key=%s", self.execution_key)

    def save_reply(self, reply: BackendReply) -> SessionRecord:
        updated = SessionRecord(
            session_id=self.state.session.session_id,
            base_key=self.state.session.base_key,
            backend=self.state.session.backend,
            cwd=self.state.session.cwd,
            label=self.state.session.label,
            model_override=self.state.session.model_override,
            safety_mode=self.state.session.safety_mode,
            native_session_id=reply.native_session_id or self.state.session.native_session_id,
            release_channel=self.state.session.release_channel,
            last_usage=reply.metadata.get("usage", {}) if isinstance(reply.metadata, dict) else {},
            created_at=self.state.session.created_at,
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
        self.state.session = updated
        return updated
