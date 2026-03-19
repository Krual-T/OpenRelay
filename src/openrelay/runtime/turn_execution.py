from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping

from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.core import IncomingMessage, SessionRecord
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

    def supports_backend(self, backend: str) -> bool:
        return self.runtime_service is not None and backend in self.runtime_backends
