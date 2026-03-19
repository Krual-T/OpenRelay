from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping

from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.core import IncomingMessage, SessionRecord
from openrelay.presentation.live_turn import LiveTurnPresenter

from .turn import TurnRuntimeContext
from .turn_application import TurnApplicationService
from .turn_run_controller import TurnRunController
from .turn_runtime_event_bridge import TurnRuntimeEventBridge

DEFAULT_IMAGE_PROMPT = "用户发送了图片。请先查看图片内容，再根据图片直接回答用户。"


@dataclass(slots=True)
class RuntimeTurnExecutionService:
    runtime_context: TurnRuntimeContext
    runtime_backends: Mapping[str, object]
    reply: Callable[[IncomingMessage, str, bool, str], Awaitable[None]]
    runtime_service: AgentRuntimeService | None = None

    async def run(self, message: IncomingMessage, execution_key: str, session: SessionRecord) -> None:
        if not self.supports_backend(session.backend):
            await self.reply(message, f"Unsupported backend: {session.backend}")
            return

        presenter = self.runtime_context.live_turn_presenter or LiveTurnPresenter()
        controller = TurnRunController(self.runtime_context, message, execution_key, presenter)
        controller.initialize(session)
        application = TurnApplicationService(
            self.runtime_context,
            message,
            execution_key,
            controller,
            TurnRuntimeEventBridge(self.runtime_context, controller, presenter),
        )
        await application.run(self.message_summary_text(message), self.build_backend_prompt(message))

    def supports_backend(self, backend: str) -> bool:
        return self.runtime_service is not None and backend in self.runtime_backends

    def message_summary_text(self, message: IncomingMessage) -> str:
        text = str(message.text or "").strip()
        if text:
            return text
        if message.local_image_paths:
            count = len(message.local_image_paths)
            return "[图片]" if count == 1 else f"[图片 x{count}]"
        return ""

    def build_backend_prompt(self, message: IncomingMessage) -> str:
        text = str(message.text or "").strip()
        if message.local_image_paths and text in {"", "[图片]"}:
            return DEFAULT_IMAGE_PROMPT
        return text
