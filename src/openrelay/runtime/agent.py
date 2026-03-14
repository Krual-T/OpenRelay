from __future__ import annotations

import asyncio
import copy
from collections import defaultdict, deque
from dataclasses import dataclass
import logging
import os
import sys
from typing import Any, Awaitable, Callable

from openrelay.backends import Backend, BackendDescriptor, BackendContext, CodexBackend, build_builtin_backend_descriptors, instantiate_builtin_backends
from openrelay.core import (
    ActiveRun,
    AppConfig,
    IncomingMessage,
    SessionRecord,
    append_release_event,
    build_release_session_label,
    build_release_switch_note,
    format_release_channel,
    get_release_workspace,
    get_session_workspace_root,
    infer_release_channel,
    utc_now,
)
from openrelay.feishu import FeishuMessenger, FeishuStreamingSession, FeishuTypingManager, build_streaming_content
from openrelay.session import SessionBrowser, SessionLifecycleResolver, SessionScopeResolver, SessionSortMode, SessionUX, build_session_list_card
from openrelay.storage import StateStore

from .commands import PanelCommandArgs, RuntimeCommandHooks, RuntimeCommandRouter
from .follow_up import QueuedFollowUp
from .help import HelpRenderer
from .interactions import RunInteractionController
from .live import apply_live_progress, build_process_panel_text, build_reply_card, create_live_reply_state
from .panel import build_panel_card
from .restart import RuntimeRestartController, get_systemd_service_unit, is_systemd_service_process
NON_BLOCKING_ACTIVE_RUN_COMMANDS = {"/ping", "/status", "/usage", "/help", "/tools", "/panel", "/restart"}
DEFAULT_IMAGE_PROMPT = "用户发送了图片。请先查看图片内容，再根据图片直接回答用户。"
LOGGER = logging.getLogger("openrelay.runtime")


@dataclass(slots=True)
class _ReplyRoute:
    reply_to_message_id: str
    root_id: str
    force_new_message: bool = False


class _BackendTurnSession:
    def __init__(self, runtime: AgentRuntime, message: IncomingMessage, execution_key: str, session: SessionRecord):
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
        self.live_state = create_live_reply_state(session, runtime.session_ux.format_cwd)
        if session.backend != "codex":
            self.live_state["heading"] = "Generating reply"
            self.live_state["status"] = "Waiting for streamed output"

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
            root_id=self.runtime._root_id_for_message(self.message),
            action_context=self.runtime._build_card_action_context(self.message, self.session.base_key),
            reply_target_getter=self.reply_target_message_id,
            emit_progress=self.on_progress,
            send_text=lambda text: self.runtime.messenger.send_text(
                self.message.chat_id,
                text,
                reply_to_message_id=self.reply_target_message_id(),
                root_id=self.runtime._root_id_for_message(self.message),
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

    def build_backend_context(self) -> BackendContext:
        return BackendContext(
            workspace_root=get_session_workspace_root(self.runtime.config, self.session),
            local_image_paths=self.message.local_image_paths,
            cancel_event=self.cancel_event,
            on_partial_text=self.on_partial_text,
            on_progress=self.on_progress,
            on_thread_started=self.persist_native_thread_id,
            on_server_request=self.interaction_controller.request if self.interaction_controller is not None else None,
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

    def reply_target_message_id(self) -> str:
        if self.streaming is not None and self.streaming.has_started() and self.streaming.message_id():
            return self.streaming.message_id()
        return self.message.reply_to_message_id or ("" if self.runtime._is_card_action_message(self.message) else self.message.message_id)

    async def save_reply(self, reply: Any) -> SessionRecord:
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
        await self.runtime._reply_final(self.message, text, self.streaming, self.live_state)

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
                self.streaming = self.runtime.streaming_session_factory(self.runtime.messenger)
                await self.streaming.start(
                    self.message.chat_id,
                    reply_to_message_id=self.message.reply_to_message_id or ("" if self.runtime._is_card_action_message(self.message) else self.message.message_id),
                    root_id=self.runtime._root_id_for_message(self.message),
                )
                self.runtime._remember_outbound_aliases(self.message, self.runtime.build_session_key(self.message), [self.streaming.message_alias_ids()])
            if not self.streaming.is_active():
                return
            await self.streaming.update(snapshot)
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


class AgentRuntime:
    def __init__(
        self,
        config: AppConfig,
        store: StateStore,
        messenger: FeishuMessenger,
        backends: dict[str, Backend] | None = None,
        backend_descriptors: dict[str, BackendDescriptor] | None = None,
        streaming_session_factory: Callable[[FeishuMessenger], FeishuStreamingSession] | None = None,
        typing_manager: FeishuTypingManager | None = None,
    ):
        self.config = config
        self.store = store
        self.messenger = messenger
        self.backend_descriptors = backend_descriptors or build_builtin_backend_descriptors()
        self.backends = backends or instantiate_builtin_backends(config, self.backend_descriptors)
        if config.backend.default_backend not in self.backends:
            raise ValueError(f"Configured default backend is unavailable: {config.backend.default_backend}")
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._pending_session_inputs: dict[str, deque[IncomingMessage | QueuedFollowUp]] = defaultdict(deque)
        self.active_runs: dict[str, ActiveRun] = {}
        self.streaming_session_factory = streaming_session_factory or (lambda current_messenger: FeishuStreamingSession(current_messenger))
        self.typing_manager = typing_manager or FeishuTypingManager(messenger)
        self.session_browser = SessionBrowser(config, store)
        self.session_ux = SessionUX(config, store)
        self.session_scope = SessionScopeResolver(config, store, LOGGER)
        self.session_lifecycle = SessionLifecycleResolver(config, store)
        self.help_renderer = HelpRenderer(config, store, self.session_ux)
        self.command_router = RuntimeCommandRouter(
            config,
            store,
            self.session_browser,
            self.session_ux,
            self.help_renderer,
            self.backends,
            RuntimeCommandHooks(
                reply=self._reply,
                send_help=self._send_help,
                send_panel=self._send_panel,
                send_session_list=self._send_session_list,
                switch_release_channel=self._switch_release_channel,
                stop=self._handle_stop,
                schedule_restart=self._schedule_restart,
                is_admin=self.is_admin,
                available_backend_names=self.available_backend_names,
            ),
        )
        self.restart_controller = RuntimeRestartController(LOGGER)

    async def shutdown(self) -> None:
        await CodexBackend.shutdown_all()
        await self.messenger.close()
        self.store.close()

    def _compose_session_key(self, message: IncomingMessage, *, thread_id: str = "") -> str:
        return self.session_scope.compose_key(message, thread_id=thread_id)

    def _thread_session_key_candidates(self, message: IncomingMessage) -> list[str]:
        return self.session_scope.thread_candidates(message)

    def _is_command_message(self, message: IncomingMessage) -> bool:
        return self.session_scope.is_command_message(message)

    def _is_top_level_message(self, message: IncomingMessage) -> bool:
        return self.session_scope.is_top_level_message(message)

    def _is_top_level_control_command(self, message: IncomingMessage) -> bool:
        return self.session_scope.is_top_level_control_command(message)

    def build_session_key(self, message: IncomingMessage) -> str:
        return self.session_scope.build_session_key(message)

    def _remember_thread_session_alias(self, message: IncomingMessage, session_key: str) -> None:
        self.session_scope.remember_inbound_aliases(message, session_key)

    def _remember_outbound_aliases(
        self,
        message: IncomingMessage,
        session_key: str,
        alias_groups: tuple[tuple[str, ...], ...] | list[tuple[str, ...]],
    ) -> None:
        self.session_scope.remember_outbound_aliases(message, session_key, alias_groups)

    def is_allowed_user(self, sender_open_id: str) -> bool:
        if sender_open_id in self.config.feishu.admin_open_ids:
            return True
        if not self.config.feishu.allowed_open_ids:
            return True
        return sender_open_id in self.config.feishu.allowed_open_ids

    def is_admin(self, sender_open_id: str) -> bool:
        return bool(self.config.feishu.admin_open_ids) and sender_open_id in self.config.feishu.admin_open_ids

    def _build_execution_key(self, session_key: str, session: SessionRecord, *, force_session_scope: bool = False) -> str:
        return f"session:{session.session_id}"

    def _load_session_for_message(self, message: IncomingMessage, session_key: str) -> SessionRecord:
        return self.session_lifecycle.load_for_message(
            session_key,
            is_top_level_control_command=self._is_top_level_control_command(message),
            is_top_level_message=self._is_top_level_message(message),
            control_key=self._compose_session_key(message),
        )

    def _resolve_stop_execution_key(self, message: IncomingMessage, session_key: str, session: SessionRecord) -> str:
        return self._build_execution_key(session_key, session)

    def _message_summary_text(self, message: IncomingMessage) -> str:
        text = str(message.text or "").strip()
        if text:
            return text
        if message.local_image_paths:
            count = len(message.local_image_paths)
            return "[图片]" if count == 1 else f"[图片 x{count}]"
        return ""

    def _build_backend_prompt(self, message: IncomingMessage) -> str:
        text = str(message.text or "").strip()
        if message.local_image_paths and text in {"", "[图片]"}:
            return DEFAULT_IMAGE_PROMPT
        return text

    async def dispatch_message(self, message: IncomingMessage) -> None:
        try:
            if not self._message_summary_text(message):
                return
            if self.config.feishu.bot_open_id and message.sender_open_id == self.config.feishu.bot_open_id:
                return
            if self.store.remember_message(message.event_id or message.message_id):
                return
            if not message.actionable:
                return
            if not self.is_allowed_user(message.sender_open_id):
                await self._reply(message, "你没有权限使用 openrelay。", command_reply=True)
                return

            session_key = self.build_session_key(message)
            self._remember_thread_session_alias(message, session_key)
            session = self._load_session_for_message(message, session_key)
            LOGGER.info(
                "dispatch resolved session event_id=%s message_id=%s session_key=%s session_id=%s native_session_id=%s root_id=%s thread_id=%s parent_id=%s",
                message.event_id,
                message.message_id,
                session_key,
                session.session_id,
                session.native_session_id,
                message.root_id,
                message.thread_id,
                message.parent_id,
            )
            execution_key = self._build_execution_key(
                session_key,
                session,
                force_session_scope=self._is_top_level_control_command(message),
            )
            if self._is_stop_command(message.text):
                await self._handle_stop(message, self._resolve_stop_execution_key(message, session_key, session))
                return

            session_lock = self._locks[execution_key]
            if session_lock.locked() and self._should_bypass_active_run(message.text):
                handled = await self._handle_command(message, session_key, session)
                if handled:
                    return
            active = self.active_runs.get(execution_key)
            if session_lock.locked() and active is not None and active.try_handle_input is not None:
                if await active.try_handle_input(message):
                    return
            if session_lock.locked():
                queued_follow_up = self._enqueue_pending_input(execution_key, message)
                if queued_follow_up is not None:
                    await self._reply(message, queued_follow_up.acknowledgement_text())
                return

            async with session_lock:
                await self._handle_message_serialized(message, execution_key)
        except Exception:
            LOGGER.exception("dispatch_message failed for event_id=%s chat_id=%s", message.event_id, message.chat_id)

    async def _handle_message_serialized(self, message: IncomingMessage, execution_key: str) -> None:
        pending_input: IncomingMessage | QueuedFollowUp | None = message
        while pending_input is not None:
            await self._handle_single_serialized_input(pending_input, execution_key)
            pending_input = self._dequeue_pending_input(execution_key)

    async def _handle_single_serialized_input(self, pending_input: IncomingMessage | QueuedFollowUp, execution_key: str) -> None:
        message = pending_input.to_message() if isinstance(pending_input, QueuedFollowUp) else pending_input
        session_key = self.build_session_key(message)
        self._remember_thread_session_alias(message, session_key)
        session = self._load_session_for_message(message, session_key)
        LOGGER.info(
            "serialized input resolved session event_id=%s message_id=%s session_key=%s session_id=%s native_session_id=%s",
            message.event_id,
            message.message_id,
            session_key,
            session.session_id,
            session.native_session_id,
        )
        if message.text.startswith("/"):
            handled = await self._handle_command(message, session_key, session)
            if handled:
                return
        await self._run_backend_turn(message, execution_key, session)

    def _enqueue_pending_input(self, execution_key: str, message: IncomingMessage) -> QueuedFollowUp | None:
        pending_inputs = self._pending_session_inputs[execution_key]
        if self.active_runs.get(execution_key) is not None and not message.text.startswith("/"):
            last_input = pending_inputs[-1] if pending_inputs else None
            if isinstance(last_input, QueuedFollowUp):
                last_input.merge(message)
                return last_input
            queued_follow_up = QueuedFollowUp.from_message(message)
            pending_inputs.append(queued_follow_up)
            return queued_follow_up
        pending_inputs.append(message)
        return None

    def _dequeue_pending_input(self, execution_key: str) -> IncomingMessage | QueuedFollowUp | None:
        pending_inputs = self._pending_session_inputs.get(execution_key)
        if not pending_inputs:
            return None
        next_input = pending_inputs.popleft()
        if not pending_inputs:
            self._pending_session_inputs.pop(execution_key, None)
        return next_input

    def _queued_follow_up_count(self, execution_key: str) -> int:
        pending_inputs = self._pending_session_inputs.get(execution_key)
        if not pending_inputs:
            return 0
        return sum(item.message_count for item in pending_inputs if isinstance(item, QueuedFollowUp))

    async def _run_backend_turn(self, message: IncomingMessage, execution_key: str, session: SessionRecord) -> None:
        backend = self.backends.get(session.backend)
        if backend is None:
            await self._reply(message, f"Unsupported backend: {session.backend}")
            return

        message_summary = self._message_summary_text(message)
        backend_prompt = self._build_backend_prompt(message)
        turn = _BackendTurnSession(self, message, execution_key, session)

        try:
            await turn.prepare(message_summary)
            turn.build_interaction_controller()
            self.active_runs[execution_key] = turn.activate_run(message_summary)

            reply = await backend.run(
                turn.session,
                backend_prompt,
                turn.build_backend_context(),
            )
            await turn.save_reply(reply)
            await turn.reply_final(reply.text or "(empty reply)")
        except Exception as exc:
            if "interrupted by /stop" in str(exc).lower() or "interrupted" in str(exc).lower():
                await turn.reply_final("已停止当前回复。")
            else:
                await turn.reply_final(f"处理失败：{exc}")
        finally:
            self.active_runs.pop(execution_key, None)
            await turn.finalize()

    async def _handle_command(self, message: IncomingMessage, session_key: str, session: SessionRecord) -> bool:
        return await self.command_router.handle(message, session_key, session)

    async def _handle_stop(self, message: IncomingMessage, execution_key: str) -> None:
        active = self.active_runs.get(execution_key)
        if active is None:
            await self._reply(message, "当前没有进行中的回复。", command_reply=True)
            return
        await active.cancel("interrupted by /stop")
        queued_follow_up_count = self._queued_follow_up_count(execution_key)
        stop_message = "已发送停止请求，正在中断当前回复。"
        if queued_follow_up_count > 0:
            stop_message = f"{stop_message[:-1]} 停止后会继续处理已收到的 {queued_follow_up_count} 条补充消息。"
        await self._reply(message, stop_message, command_reply=True)

    async def _switch_release_channel(
        self,
        message: IncomingMessage,
        session_key: str,
        session: SessionRecord,
        target_channel: str,
        command_name: str,
        reason: str = "",
    ) -> None:
        workspace_dir = get_release_workspace(self.config, target_channel)
        if not workspace_dir.exists():
            await self._reply(message, f"{target_channel} 工作目录不存在：{workspace_dir}", command_reply=True)
            return
        active = self.active_runs.get(self._build_execution_key(session.base_key, session))
        cancelled_active_run = active is not None
        if active is not None:
            await active.cancel(f"interrupted by {command_name}")
        next_session = self.store.create_next_session(session_key, session, build_release_session_label(target_channel))
        next_session.release_channel = target_channel
        next_session.cwd = str(workspace_dir)
        next_session.native_session_id = ""
        if target_channel == "main":
            next_session.safety_mode = "read-only"
        self.store.save_session(next_session)
        event = append_release_event(
            self.config,
            {
                "type": "release.force-stable" if target_channel == "main" else "release.switch",
                "command": command_name,
                "reason": reason,
                "session_key": session_key,
                "chat_id": message.chat_id,
                "operator_open_id": message.sender_open_id,
                "from_channel": infer_release_channel(self.config, session),
                "to_channel": target_channel,
                "previous_session_id": session.session_id,
                "next_session_id": next_session.session_id,
                "previous_cwd": session.cwd,
                "next_cwd": next_session.cwd,
                "previous_model": self.session_ux.effective_model(session),
                "next_model": self.session_ux.effective_model(next_session),
                "previous_sandbox": session.safety_mode,
                "next_sandbox": next_session.safety_mode,
                "cancelled_active_run": cancelled_active_run,
            },
        )
        self.store.append_message(next_session.session_id, "assistant", build_release_switch_note(event))
        await self._reply(
            message,
            "\n".join(
                filter(
                    None,
                    [
                        "已强制切到 main 稳定版本。" if target_channel == "main" else "已切到 develop 修复版本。",
                        f"session_id={next_session.session_id}",
                        f"channel={format_release_channel(target_channel)}",
                        f"cwd={self.session_ux.format_cwd(next_session.cwd, next_session)}",
                        f"sandbox={next_session.safety_mode}",
                        f"reason={reason}" if reason else "",
                        "已中断上一条进行中的回复。" if cancelled_active_run else "",
                        "已写入切换记录，后续智能体可据此继续修复。",
                    ],
                )
            ),
            command_reply=True,
        )

    def _build_card_action_context(self, message: IncomingMessage, session_key: str) -> dict[str, str]:
        return {
            "rootId": message.root_id,
            "threadId": message.thread_id or message.root_id,
            "sessionKey": session_key,
            "sessionOwnerOpenId": message.session_owner_open_id or (message.sender_open_id if message.chat_type == "group" and self.config.feishu.group_session_scope != "shared" else ""),
        }

    async def _send_help(self, message: IncomingMessage, session_key: str, session: SessionRecord) -> None:
        card = self.help_renderer.build_card(session, self.available_backend_names(), self._build_card_action_context(message, session_key))
        try:
            await self.messenger.send_interactive_card(
                message.chat_id,
                card,
                reply_to_message_id=self._command_reply_target(message),
                root_id=self._root_id_for_message(message),
                force_new_message=self._should_force_new_message_for_command_card(message),
                update_message_id=self._command_card_update_target(message),
            )
        except Exception:
            await self._reply(message, self.help_renderer.build_text(session, self.available_backend_names()), command_reply=True, command_name="/help")

    async def _send_panel(self, message: IncomingMessage, session_key: str, session: SessionRecord, args: PanelCommandArgs) -> None:
        panel_info = self._build_panel_base_info(message, session_key, session, args.view)
        fallback_text = ""
        if args.view == "sessions":
            session_page = self.session_browser.list_page(session_key, session, page=args.page, sort_mode=args.sort_mode)
            card = build_panel_card(
                {
                    **panel_info,
                    "page": session_page.page,
                    "total_pages": session_page.total_pages,
                    "sort_mode": session_page.sort_mode,
                    "sessions": self.session_ux.build_session_display_entries(session_page.entries, start_index=session_page.start_index),
                }
            )
            fallback_text = self._build_panel_sessions_text(session_page)
        elif args.view == "directories":
            directory_shortcuts = self.session_ux.build_directory_shortcut_entries(session)
            card = build_panel_card({**panel_info, "directory_shortcuts": directory_shortcuts})
            fallback_text = self._build_panel_directories_text(directory_shortcuts)
        elif args.view == "commands":
            command_entries = self._build_panel_command_entries()
            card = build_panel_card({**panel_info, "command_entries": command_entries})
            fallback_text = self._build_panel_commands_text(command_entries)
        elif args.view == "status":
            status_entries = self._build_panel_status_entries(session)
            card = build_panel_card({**panel_info, "status_entries": status_entries})
            fallback_text = self._build_panel_status_text(status_entries)
        else:
            entries = self.session_browser.list_entries(session_key, session, limit=6)
            directory_shortcuts = self.session_ux.build_directory_shortcut_entries(session)
            card = build_panel_card(
                {
                    **panel_info,
                    "sessions": self.session_ux.build_session_display_entries(entries),
                    "directory_shortcuts": directory_shortcuts,
                }
            )
            fallback_text = self._build_panel_home_text(session, entries, directory_shortcuts)
        try:
            await self.messenger.send_interactive_card(
                message.chat_id,
                card,
                reply_to_message_id=self._command_reply_target(message),
                root_id=self._root_id_for_message(message),
                force_new_message=self._should_force_new_message_for_command_card(message),
                update_message_id=self._command_card_update_target(message),
            )
        except Exception:
            await self._reply(message, fallback_text, command_reply=True, command_name="/panel")

    async def _send_session_list(self, message: IncomingMessage, session_key: str, session: SessionRecord, page: int, sort_mode: SessionSortMode) -> None:
        session_page = self.session_browser.list_page(session_key, session, page=page, sort_mode=sort_mode)
        card = build_session_list_card(
            {
                "session_id": session.session_id,
                "current_title": self.session_ux.build_session_title(session.label, session.session_id),
                "channel": format_release_channel(infer_release_channel(self.config, session)),
                "cwd": self.session_ux.format_cwd(session.cwd, session),
                "page": session_page.page,
                "total_pages": session_page.total_pages,
                "total_entries": session_page.total_entries,
                "sort_mode": session_page.sort_mode,
                "has_previous": session_page.has_previous,
                "has_next": session_page.has_next,
                "action_context": self._build_card_action_context(message, session_key),
                "sessions": self.session_ux.build_session_display_entries(session_page.entries, start_index=session_page.start_index),
            }
        )
        try:
            await self.messenger.send_interactive_card(
                message.chat_id,
                card,
                reply_to_message_id=self._command_reply_target(message),
                root_id=self._root_id_for_message(message),
                force_new_message=self._should_force_new_message_for_command_card(message),
                update_message_id=self._command_card_update_target(message),
            )
        except Exception:
            await self._reply(message, self.session_ux.format_session_list_page(session_page), command_reply=True, command_name="/resume")

    def _build_panel_base_info(self, message: IncomingMessage, session_key: str, session: SessionRecord, view: str) -> dict[str, Any]:
        return {
            "view": view,
            "session_id": session.session_id,
            "current_title": self.session_ux.build_session_title(session.label, session.session_id),
            "channel": format_release_channel(infer_release_channel(self.config, session)),
            "cwd": self.session_ux.format_cwd(session.cwd, session),
            "model": self.session_ux.effective_model(session),
            "provider": self.backend_descriptors.get(session.backend).transport if session.backend in self.backend_descriptors else "-",
            "sandbox": session.safety_mode,
            "context_usage": self.session_ux.format_context_usage(session),
            "context_preview": self.session_ux.build_context_preview(session),
            "action_context": self._build_card_action_context(message, session_key),
        }

    def _build_panel_command_entries(self) -> list[dict[str, str]]:
        return [
            {
                "title": "恢复上一条",
                "meta": "会话 · 最短继续路径",
                "preview": "直接回到最近会话，不必先打开列表。",
                "command": "/resume latest",
                "action_label": "恢复上一条",
                "action_type": "primary",
            },
            {
                "title": "浏览会话结果",
                "meta": "会话 · 翻页 / 排序",
                "preview": "在面板里看最近会话，再决定恢复哪一条。",
                "command": "/panel sessions",
                "action_label": "看会话",
            },
            {
                "title": "浏览目录结果",
                "meta": "目录 · 快捷入口",
                "preview": "优先点快捷目录；没有合适入口时再手写 /cwd。",
                "command": "/panel directories",
                "action_label": "看目录",
            },
            {
                "title": "管理快捷目录",
                "meta": "目录 · 新增 / 列表 / 快速切换",
                "preview": "用 /shortcut add|list|cd 在飞书里维护自己的常用目录入口。",
                "command": "/shortcut list",
                "action_label": "看快捷目录",
            },
            {
                "title": "查看完整状态",
                "meta": "状态 · 目录 / 模型 / 上下文",
                "preview": "先确认现场，再决定继续当前任务还是切上下文。",
                "command": "/status",
                "action_label": "看状态",
            },
            {
                "title": "新建隔离会话",
                "meta": "隔离 · 新任务 / 切话题",
                "preview": "当目标已经变了时，不要继续堆在当前会话里。",
                "command": "/new",
                "action_label": "新会话",
            },
            {
                "title": "打开帮助",
                "meta": "引导 · 下一步建议",
                "preview": "需要 prompt 示例或命令速查时使用。",
                "command": "/help",
                "action_label": "打开帮助",
            },
        ]

    def _build_panel_status_entries(self, session: SessionRecord) -> list[dict[str, str]]:
        channel = format_release_channel(infer_release_channel(self.config, session))
        cwd = self.session_ux.format_cwd(session.cwd, session)
        context_preview = self.session_ux.build_context_preview(session) or "还没有可总结的本地上下文。"
        return [
            {
                "title": "当前会话状态",
                "meta": f"{channel} · 目录 {cwd} · sandbox {session.safety_mode}",
                "preview": f"模型 {self.session_ux.effective_model(session)} · 后端线程 {session.native_session_id or 'pending'}",
                "command": "/status",
                "action_label": "完整状态",
                "action_type": "primary",
            },
            {
                "title": "上下文与用量",
                "meta": f"context_usage={self.session_ux.format_context_usage(session)}",
                "preview": context_preview,
                "command": "/usage",
                "action_label": "查看用量",
            },
            {
                "title": "继续当前任务",
                "meta": "如果目标没变，通常直接发消息最快",
                "preview": "要找旧会话就去会话结果；要切目录就去目录结果；不确定下一步时再打开帮助。",
                "command": "/help",
                "action_label": "打开帮助",
            },
        ]

    def _build_panel_home_text(self, session: SessionRecord, entries: list[Any], directory_shortcuts: list[dict[str, str]]) -> str:
        lines = [
            self.session_ux.build_panel_text(session),
            "",
            "结果面：/panel sessions | /panel directories | /panel commands | /panel status",
            "",
            "最近会话：",
            self.session_ux.format_session_list(entries[:3]),
        ]
        if directory_shortcuts:
            lines.extend(["", "目录入口："])
            lines.extend([f"- {entry['label']} -> {entry['display_path']}" for entry in directory_shortcuts[:3]])
        else:
            lines.extend(["", "目录入口：暂无快捷目录；可先 /cwd <path>。"])
        return "\n".join(lines)

    def _build_panel_sessions_text(self, session_page: Any) -> str:
        return "\n".join([
            "OpenRelay 面板 · 会话",
            self.session_ux.format_session_list_page(session_page),
            "",
            "返回总览：/panel。",
        ])

    def _build_panel_directories_text(self, directory_shortcuts: list[dict[str, str]]) -> str:
        lines = [
            "OpenRelay 面板 · 目录",
            "优先点快捷目录；没有合适入口时，再手写 /cwd <path>。",
        ]
        if directory_shortcuts:
            lines.extend([f"- {entry['label']} -> {entry['display_path']}" for entry in directory_shortcuts])
        else:
            lines.append("- 当前没有配置快捷目录。")
        lines.extend(["", "常用动作：/cwd /main /develop"])
        return "\n".join(lines)

    def _build_panel_commands_text(self, command_entries: list[dict[str, str]]) -> str:
        lines = ["OpenRelay 面板 · 命令", "高频动作："]
        lines.extend([f"- {entry['title']}：{entry['preview']} ({entry['command']})" for entry in command_entries])
        return "\n".join(lines)

    def _build_panel_status_text(self, status_entries: list[dict[str, str]]) -> str:
        lines = ["OpenRelay 面板 · 状态", "先看现场，再决定下一步："]
        lines.extend([f"- {entry['title']}：{entry['preview']} ({entry['command']})" for entry in status_entries])
        return "\n".join(lines)

    async def _reply_final(
        self,
        message: IncomingMessage,
        text: str,
        streaming: FeishuStreamingSession | None,
        live_state: dict[str, Any] | None = None,
    ) -> None:
        live_state = live_state or {}
        process_text = build_process_panel_text(live_state)
        if self.config.feishu.stream_mode == "card" and streaming is not None and streaming.has_started():
            try:
                await streaming.close(
                    build_reply_card(
                        text,
                        "openrelay 回复",
                        process_text=process_text,
                    )
                )
                return
            except Exception:
                LOGGER.exception("streaming final card update failed for event_id=%s", message.event_id)
        await self._send_text_reply(message, text, self._build_default_reply_route(message))

    async def _reply(self, message: IncomingMessage, text: str, command_reply: bool = False, command_name: str = "") -> None:
        route = self._build_command_reply_route(message, command_name) if command_reply else self._build_default_reply_route(message)
        await self._send_text_reply(message, text, route)

    def available_backend_names(self) -> list[str]:
        return sorted(self.backends)

    async def _send_text_reply(self, message: IncomingMessage, text: str, route: _ReplyRoute) -> None:
        sent_messages = await self.messenger.send_text(
            message.chat_id,
            text,
            reply_to_message_id=route.reply_to_message_id,
            root_id=route.root_id,
            force_new_message=route.force_new_message,
        )
        session_key = self.build_session_key(message)
        self._remember_outbound_aliases(message, session_key, [sent_message.alias_ids() for sent_message in sent_messages])

    def _build_default_reply_route(self, message: IncomingMessage) -> _ReplyRoute:
        return _ReplyRoute(
            reply_to_message_id=message.reply_to_message_id or ("" if self._is_card_action_message(message) else message.message_id),
            root_id=self._root_id_for_message(message),
        )

    def _build_command_reply_route(self, message: IncomingMessage, command_name: str) -> _ReplyRoute:
        return _ReplyRoute(
            reply_to_message_id=self._command_reply_target(message),
            root_id=self._root_id_for_message(message),
            force_new_message=self._should_force_new_message_for_command(message, command_name),
        )

    def _command_reply_target(self, message: IncomingMessage) -> str:
        return message.reply_to_message_id or ("" if self._is_card_action_message(message) else message.message_id)

    def _command_card_update_target(self, message: IncomingMessage) -> str:
        if not self._is_card_action_message(message):
            return ""
        return message.reply_to_message_id

    def _root_id_for_message(self, message: IncomingMessage) -> str:
        return self.session_scope.root_id_for_message(message)

    def _is_card_action_message(self, message: IncomingMessage) -> bool:
        return self.session_scope.is_card_action_message(message)

    def _is_top_level_p2p_command(self, message: IncomingMessage) -> bool:
        return message.chat_type == "p2p" and not message.root_id and not message.thread_id

    def _should_force_new_message_for_command(self, message: IncomingMessage, command_name: str) -> bool:
        if not self._is_top_level_p2p_command(message):
            return False
        return command_name not in {"/cwd", "/cd"}

    def _should_force_new_message_for_command_card(self, message: IncomingMessage) -> bool:
        return self._is_top_level_p2p_command(message) and not self._is_card_action_message(message)

    def _is_stop_command(self, text: str) -> bool:
        return text.strip().lower().startswith("/stop")

    def _should_bypass_active_run(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped.startswith("/"):
            return False
        command = stripped.split(maxsplit=1)[0].lower()
        if command in NON_BLOCKING_ACTIVE_RUN_COMMANDS:
            return True
        if command != "/resume":
            return False
        tokens = stripped.split(maxsplit=2)
        return len(tokens) == 1 or tokens[1].lower() == "list"

    def _schedule_restart(self) -> None:
        self.restart_controller.schedule_restart(self._restart_process())

    async def _restart_process(self) -> None:
        await asyncio.sleep(0.4)
        if is_systemd_service_process():
            unit_name = get_systemd_service_unit()
            try:
                await self._restart_systemd_service(unit_name)
                return
            except Exception:
                self.restart_controller.mark_failed()
                LOGGER.exception("failed to restart %s via systemd", unit_name)
                raise
        try:
            await CodexBackend.shutdown_all()
        except Exception:
            LOGGER.exception("failed shutting down backends before restart")
        try:
            os.execvpe(sys.executable, [sys.executable, "-m", "openrelay"], os.environ)
        except Exception:
            self.restart_controller.mark_failed()
            LOGGER.exception("failed to restart openrelay process")
            raise

    async def _restart_systemd_service(self, unit_name: str) -> None:
        process = await asyncio.create_subprocess_exec(
            "systemctl",
            "--user",
            "--no-block",
            "restart",
            unit_name,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=dict(os.environ),
        )
        stderr = b""
        if process.stderr is not None:
            stderr = await process.stderr.read()
        exit_code = await process.wait()
        if exit_code == 0:
            return
        detail = stderr.decode("utf-8", errors="replace").strip()
        message = detail or f"systemctl --user restart exited with code {exit_code}"
        raise RuntimeError(message)
