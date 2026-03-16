from __future__ import annotations

import logging
from typing import Any
from typing import Callable

from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.backends import BackendDescriptor, build_builtin_backend_descriptors
from openrelay.backends.codex import CodexAppServerClient
from openrelay.backends.codex_adapter.backend import CodexRuntimeBackend
from openrelay.core import (
    AppConfig,
    IncomingMessage,
    SessionRecord,
)
from openrelay.feishu import FeishuMessenger, FeishuStreamingSession, FeishuTypingManager
from openrelay.presentation.live_turn import LiveTurnPresenter
from openrelay.presentation.panel import RuntimePanelPresenter
from openrelay.presentation.runtime_status import RuntimeStatusPresenter
from openrelay.presentation.session import SessionPresentation
from openrelay.release import ReleaseCommandService
from openrelay.session import (
    SessionBrowser,
    SessionBindingStore,
    SessionLifecycleResolver,
    SessionMutationService,
    SessionScopeResolver,
    SessionShortcutService,
    SessionWorkspaceService,
)
from openrelay.storage import StateStore

from .commands import RuntimeCommandHooks, RuntimeCommandRouter
from .execution import ExecutionInput, RuntimeExecutionCoordinator
from .follow_up import QueuedFollowUp
from .help import HelpRenderer
from .help_service import RuntimeHelpService
from .live import build_process_panel_text, build_reply_card
from .panel_service import RuntimePanelService
from .replying import ReplyRoute, RuntimeReplyPolicy
from .restart import RuntimeRestartController
from .turn import BackendTurnSession, TurnRuntimeContext
NON_BLOCKING_ACTIVE_RUN_COMMANDS = {"/ping", "/status", "/usage", "/help", "/tools", "/panel", "/restart"}
DEFAULT_IMAGE_PROMPT = "用户发送了图片。请先查看图片内容，再根据图片直接回答用户。"
LOGGER = logging.getLogger("openrelay.runtime")


class RuntimeOrchestrator:
    def __init__(
        self,
        config: AppConfig,
        store: StateStore,
        messenger: FeishuMessenger,
        runtime_backends: dict[str, object] | None = None,
        backend_descriptors: dict[str, BackendDescriptor] | None = None,
        streaming_session_factory: Callable[[FeishuMessenger], FeishuStreamingSession] | None = None,
        typing_manager: FeishuTypingManager | None = None,
    ):
        self.config = config
        self.store = store
        self.messenger = messenger
        self.backend_descriptors = backend_descriptors or build_builtin_backend_descriptors()
        self.binding_store = SessionBindingStore(store)
        self.runtime_backends = runtime_backends if runtime_backends is not None else self._build_builtin_runtime_backends()
        self.agent_runtime = (
            AgentRuntimeService(self.runtime_backends, self.binding_store) if self.runtime_backends else None
        )
        if config.backend.default_backend not in self.available_backend_names():
            raise ValueError(f"Configured default backend is unavailable: {config.backend.default_backend}")
        self.execution_coordinator = RuntimeExecutionCoordinator()
        self.active_runs = self.execution_coordinator.active_runs
        self.streaming_session_factory = streaming_session_factory or (lambda current_messenger: FeishuStreamingSession(current_messenger))
        self.typing_manager = typing_manager or FeishuTypingManager(messenger)
        self.session_browser = SessionBrowser(config, store)
        self.session_presentation = SessionPresentation(config, store)
        self.live_turn_presenter = LiveTurnPresenter()
        self.session_workspace = SessionWorkspaceService(config)
        self.session_shortcuts = SessionShortcutService(config, store, self.session_workspace)
        self.session_mutations = SessionMutationService(config, store, self.session_presentation)
        self.session_scope = SessionScopeResolver(config, store, LOGGER)
        self.reply_policy = RuntimeReplyPolicy(config, self.session_scope)
        self.session_lifecycle = SessionLifecycleResolver(config, store)
        self.release_command_service = ReleaseCommandService(config, store, self.session_presentation, self.session_mutations)
        self.help_renderer = HelpRenderer(config, store, self.session_presentation, self.session_workspace, self.session_shortcuts)
        self.help_service = RuntimeHelpService(
            messenger,
            self.help_renderer,
            self.reply_policy,
            self._reply_command_fallback,
        )
        self.status_presenter = RuntimeStatusPresenter(config, store, self.session_presentation)
        self.panel_presenter = RuntimePanelPresenter(
            config,
            self.backend_descriptors,
            self.session_browser,
            self.session_presentation,
            self.session_workspace,
            self.session_shortcuts,
        )
        self.panel_service = RuntimePanelService(
            config,
            messenger,
            self.backend_descriptors,
            self.session_browser,
            self.session_presentation,
            self.session_workspace,
            self.session_shortcuts,
            self.reply_policy,
            self._reply_command_fallback,
            self.panel_presenter,
            self.agent_runtime,
        )
        self.command_router = RuntimeCommandRouter(
            config,
            store,
            self.session_browser,
            self.session_scope,
            self.session_mutations,
            self.session_presentation,
            self.session_workspace,
            self.session_shortcuts,
            self.help_renderer,
            self.release_command_service,
            self.status_presenter,
            RuntimeCommandHooks(
                reply=self._reply,
                send_help=self.help_service.send_help,
                send_panel=self.panel_service.send_panel,
                send_session_list=self.panel_service.send_session_list,
                stop=self._handle_stop,
                schedule_restart=self._schedule_restart,
                is_admin=self.is_admin,
                available_backend_names=self.available_backend_names,
                cancel_active_run_for_session=self._cancel_active_run_for_session,
            ),
            self.agent_runtime,
        )
        self.restart_controller = RuntimeRestartController(LOGGER)

    async def shutdown(self) -> None:
        if self.agent_runtime is not None:
            for backend in self.runtime_backends.values():
                await backend.shutdown()
        await CodexAppServerClient.shutdown_all()
        await self.messenger.close()
        self.store.close()

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

            session_key = self.session_scope.build_session_key(message)
            self.session_scope.remember_inbound_aliases(message, session_key)
            session = self.session_lifecycle.load_for_message(
                session_key,
                is_top_level_control_command=self.session_scope.is_top_level_control_command(message),
                is_top_level_message=self.session_scope.is_top_level_message(message),
                control_key=self.session_scope.compose_key(message),
            )
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
            execution_key = self._build_execution_key(session_key, session, force_session_scope=self.session_scope.is_top_level_control_command(message))
            if self._is_stop_command(message.text):
                await self._handle_stop(message, self._resolve_stop_execution_key(message, session_key, session))
                return

            if self.execution_coordinator.is_locked(execution_key) and self._should_bypass_active_run(message.text):
                handled = await self._handle_command(message, session_key, session)
                if handled:
                    return
            if self.execution_coordinator.is_locked(execution_key) and await self.execution_coordinator.try_handle_live_input(execution_key, message):
                return
            if self.execution_coordinator.is_locked(execution_key):
                queued_follow_up = self.execution_coordinator.enqueue_pending_input(execution_key, message)
                if queued_follow_up is not None:
                    await self._reply(message, queued_follow_up.acknowledgement_text())
                return

            async with self.execution_coordinator.lock_for(execution_key):
                await self._handle_message_serialized(message, execution_key)
        except Exception:
            LOGGER.exception("dispatch_message failed for event_id=%s chat_id=%s", message.event_id, message.chat_id)

    async def _handle_message_serialized(self, message: IncomingMessage, execution_key: str) -> None:
        pending_input: ExecutionInput | None = message
        while pending_input is not None:
            await self._handle_single_serialized_input(pending_input, execution_key)
            pending_input = self.execution_coordinator.dequeue_pending_input(execution_key)

    async def _handle_single_serialized_input(self, pending_input: ExecutionInput, execution_key: str) -> None:
        message = pending_input.to_message() if isinstance(pending_input, QueuedFollowUp) else pending_input
        session_key = self.session_scope.build_session_key(message)
        self.session_scope.remember_inbound_aliases(message, session_key)
        session = self.session_lifecycle.load_for_message(
            session_key,
            is_top_level_control_command=self.session_scope.is_top_level_control_command(message),
            is_top_level_message=self.session_scope.is_top_level_message(message),
            control_key=self.session_scope.compose_key(message),
        )
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

    async def _run_backend_turn(self, message: IncomingMessage, execution_key: str, session: SessionRecord) -> None:
        if not self._supports_runtime_backend(session.backend):
            await self._reply(message, f"Unsupported backend: {session.backend}")
            return

        message_summary = self._message_summary_text(message)
        backend_prompt = self._build_backend_prompt(message)
        turn = BackendTurnSession(self._build_turn_runtime_context(), message, execution_key, session)
        await turn.run(message_summary, backend_prompt)

    async def _handle_command(self, message: IncomingMessage, session_key: str, session: SessionRecord) -> bool:
        return await self.command_router.handle(message, session_key, session)

    async def _handle_stop(self, message: IncomingMessage, execution_key: str) -> None:
        active = self.execution_coordinator.active_run(execution_key)
        if active is None:
            await self._reply(message, "当前没有进行中的回复。", command_reply=True)
            return
        await active.cancel("interrupted by /stop")
        queued_follow_up_count = self.execution_coordinator.queued_follow_up_count(execution_key)
        stop_message = "已发送停止请求，正在中断当前回复。"
        if queued_follow_up_count > 0:
            stop_message = f"{stop_message[:-1]} 停止后会继续处理已收到的 {queued_follow_up_count} 条补充消息。"
        await self._reply(message, stop_message, command_reply=True)

    async def _cancel_active_run_for_session(self, session: SessionRecord, command_name: str) -> bool:
        active = self.active_runs.get(self._build_execution_key(session.base_key, session))
        if active is None:
            return False
        await active.cancel(f"interrupted by {command_name}")
        return True

    def _build_turn_runtime_context(self) -> TurnRuntimeContext:
        return TurnRuntimeContext(
            config=self.config,
            store=self.store,
            messenger=self.messenger,
            typing_manager=self.typing_manager,
            session_ux=self.session_presentation,
            streaming_session_factory=self.streaming_session_factory,
            execution_coordinator=self.execution_coordinator,
            build_card_action_context=self.reply_policy.build_card_action_context,
            streaming_route_for_message=self.reply_policy.streaming_route,
            root_id_for_message=self.reply_policy.root_id_for_message,
            is_card_action_message=self.reply_policy.is_card_action_message,
            build_session_key=self.session_scope.build_session_key,
            remember_outbound_aliases=self.session_scope.remember_outbound_aliases,
            reply_final=self._reply_final,
            live_turn_presenter=self.live_turn_presenter,
            binding_store=self.binding_store,
            runtime_service=self.agent_runtime,
        )

    def _build_builtin_runtime_backends(self) -> dict[str, object]:
        return {
            "codex": CodexRuntimeBackend(
                self.config.backend.codex_cli_path,
                self.config.backend.default_model,
                workspace_root=self.config.workspace_root,
                sqlite_home=self.config.backend.codex_sqlite_home,
                request_timeout_seconds=self.config.backend.codex_request_timeout_seconds,
            )
        }

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
                try:
                    await streaming.close()
                except Exception:
                    LOGGER.exception("streaming fallback close failed for event_id=%s", message.event_id)
        await self._send_text_reply(message, text, self.reply_policy.default_route(message))

    async def _reply(self, message: IncomingMessage, text: str, command_reply: bool = False, command_name: str = "") -> None:
        route = self.reply_policy.command_route(message, command_name) if command_reply else self.reply_policy.default_route(message)
        await self._send_text_reply(message, text, route)

    async def _reply_command_fallback(self, message: IncomingMessage, text: str, command_name: str) -> None:
        await self._reply(message, text, command_reply=True, command_name=command_name)

    def available_backend_names(self) -> list[str]:
        return sorted(set(self.runtime_backends))

    def _supports_runtime_backend(self, backend: str) -> bool:
        return self.agent_runtime is not None and backend in self.runtime_backends

    async def _send_text_reply(self, message: IncomingMessage, text: str, route: ReplyRoute) -> None:
        sent_messages = await self.messenger.send_text(
            message.chat_id,
            text,
            reply_to_message_id=route.reply_to_message_id,
            root_id=route.root_id,
            force_new_message=route.force_new_message,
        )
        session_key = self.session_scope.build_session_key(message)
        self.session_scope.remember_outbound_aliases(message, session_key, [sent_message.alias_ids() for sent_message in sent_messages])

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
        return len(tokens) == 1

    def _schedule_restart(self) -> None:
        self.restart_controller.schedule_restart()
