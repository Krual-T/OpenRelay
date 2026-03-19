from __future__ import annotations

import logging
from typing import Callable

from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.backends import BackendDescriptor, build_builtin_backend_descriptors
from openrelay.backends.claude_adapter import ClaudeRuntimeBackend
from openrelay.backends.codex_adapter.app_server import CodexAppServerClient
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
from .execution import RuntimeExecutionCoordinator
from .help import HelpRenderer
from .help_service import RuntimeHelpService
from .message_application import RuntimeMessageApplicationService
from .message_dispatch import MessageDispatchService
from .panel_service import RuntimePanelService
from .reply_service import RuntimeReplyService
from .replying import RuntimeReplyPolicy
from .restart import RuntimeRestartController
from .turn import BackendTurnSession, TurnRuntimeContext

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
        self.reply_service = RuntimeReplyService(messenger, self.session_scope, self.reply_policy, self.live_turn_presenter)
        self.session_lifecycle = SessionLifecycleResolver(config, store)
        self.message_dispatch = MessageDispatchService(self.session_scope, self.session_lifecycle)
        self.release_command_service = ReleaseCommandService(config, store, self.session_presentation, self.session_mutations)
        self.help_renderer = HelpRenderer(config, store, self.session_presentation, self.session_workspace, self.session_shortcuts)
        self.help_service = RuntimeHelpService(
            messenger,
            self.help_renderer,
            self.reply_policy,
            self.reply_service.reply_command_fallback,
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
            self.reply_service.reply_command_fallback,
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
                reply=self.reply_service.reply,
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
        self.message_application = RuntimeMessageApplicationService(
            config=config,
            store=store,
            execution_coordinator=self.execution_coordinator,
            message_dispatch=self.message_dispatch,
            is_allowed_user=self.is_allowed_user,
            reply=self.reply_service.reply,
            handle_command=self._handle_command,
            run_backend_turn=self._run_backend_turn,
            log_dispatch_resolution=self._log_dispatch_resolution,
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
        await self.message_application.handle(message)

    def _log_dispatch_resolution(
        self,
        message: IncomingMessage,
        session_key: str,
        session: SessionRecord,
        stage: str,
    ) -> None:
        LOGGER.info(
            "%s resolved session event_id=%s message_id=%s session_key=%s session_id=%s native_session_id=%s root_id=%s thread_id=%s parent_id=%s",
            stage,
            message.event_id,
            message.message_id,
            session_key,
            session.session_id,
            session.native_session_id,
            message.root_id,
            message.thread_id,
            message.parent_id,
        )

    async def _run_backend_turn(self, message: IncomingMessage, execution_key: str, session: SessionRecord) -> None:
        if not self._supports_runtime_backend(session.backend):
            await self.reply_service.reply(message, f"Unsupported backend: {session.backend}")
            return

        message_summary = self._message_summary_text(message)
        backend_prompt = self._build_backend_prompt(message)
        turn = BackendTurnSession(self._build_turn_runtime_context(), message, execution_key, session)
        await turn.run(message_summary, backend_prompt)

    async def _handle_command(self, message: IncomingMessage, session_key: str, session: SessionRecord) -> bool:
        return await self.command_router.handle(message, session_key, session)

    async def _handle_stop(self, message: IncomingMessage, execution_key: str) -> None:
        await self.message_application.handle_stop(message, execution_key)

    async def _cancel_active_run_for_session(self, session: SessionRecord, command_name: str) -> bool:
        return await self.message_application.cancel_active_run_for_session(session, command_name)

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
            reply_final=self.reply_service.reply_final,
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
            ),
            "claude": ClaudeRuntimeBackend(
                self.config.backend.claude_cli_path,
                workspace_root=self.config.workspace_root,
                default_model=self.config.backend.default_model,
            ),
        }

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

    def _schedule_restart(self) -> None:
        self.restart_controller.schedule_restart()
