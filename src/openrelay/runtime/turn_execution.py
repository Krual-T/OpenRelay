from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping

from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.backends.codex_adapter_v2.pool import ConnectionPool, PoolFullError
from openrelay.core import IncomingMessage, SessionRecord
from openrelay.feishu import FeishuStreamingSession
from openrelay.observability import MessageTraceContext
from openrelay.presentation.live_turn import LiveTurnPresenter

from .message_content import DEFAULT_IMAGE_PROMPT, build_backend_prompt, message_summary_text
from .turn import TurnRuntimeContext
from .turn_application import TurnApplicationService
from .turn_run_controller import TurnRunController
from .turn_runtime_event_bridge import TurnRuntimeEventBridge


@dataclass(slots=True)
class RuntimeTurnExecutionService:
    runtime_context: TurnRuntimeContext
    runtime_backends: Mapping[str, object]
    reply: Callable[..., Awaitable[None]]
    runtime_service: AgentRuntimeService | None = None

    async def run(
        self,
        message: IncomingMessage,
        execution_key: str,
        session: SessionRecord,
        *,
        trace_context: MessageTraceContext | None = None,
    ) -> None:
        if not self.supports_backend(session.backend):
            await self.reply(message, f"Unsupported backend: {session.backend}", trace_context=trace_context)
            return

        # v2 path: codex backend + pool configured
        if session.backend == "codex" and self.runtime_context.v2_pool is not None:
            await self._run_v2(message, execution_key, session)
            return

        # v1 path
        presenter = self.runtime_context.live_turn_presenter or LiveTurnPresenter()
        controller = TurnRunController(self.runtime_context, message, execution_key, presenter)
        controller.initialize(session, trace_context=trace_context)
        application = TurnApplicationService(
            self.runtime_context,
            message,
            execution_key,
            controller,
            TurnRuntimeEventBridge(self.runtime_context, controller, presenter),
        )
        await application.run(message_summary_text(message), build_backend_prompt(message))

    async def _run_v2(
        self,
        message: IncomingMessage,
        execution_key: str,
        session: SessionRecord,
    ) -> None:
        """v2 路径：ConnectionPool → CodexV2Session → run_turn。"""
        pool: ConnectionPool = self.runtime_context.v2_pool  # type: ignore[assignment]
        ctx = self.runtime_context
        user_text = message_summary_text(message)

        try:
            v2_session = await pool.get_or_create(
                session.native_session_id or execution_key,
                codex_path=ctx.config.backend.codex_cli_path,
                workspace_root=ctx.config.workspace_root,
                model=session.model_override or ctx.config.backend.default_model,
                safety_mode=getattr(session, "safety_mode", None) or "workspace-write",
                sqlite_home=getattr(ctx.config.backend, "codex_sqlite_home", None),
            )
        except PoolFullError:
            await self.reply(message, "服务繁忙，请稍后重试。", trace_context=getattr(session, "trace_context", None))
            return

        streaming = ctx.streaming_session_factory(ctx.messenger)
        try:
            await v2_session.run_turn(
                user_text,
                streaming=streaming,
                model=session.model_override or None,
            )
        except Exception:
            LOGGER.exception("v2 turn failed execution_key=%s", execution_key)
            try:
                await streaming.close(None)
            except Exception:
                pass

    def supports_backend(self, backend: str) -> bool:
        return self.runtime_service is not None and backend in self.runtime_backends
