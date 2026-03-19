from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping

from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.core import IncomingMessage, SessionRecord

from .turn import BackendTurnSession, TurnRuntimeContext

DEFAULT_IMAGE_PROMPT = "用户发送了图片。请先查看图片内容，再根据图片直接回答用户。"


@dataclass(slots=True)
class RuntimeTurnExecutionService:
    runtime_context: TurnRuntimeContext
    runtime_backends: Mapping[str, object]
    reply: Callable[[IncomingMessage, str, bool, str], Awaitable[None]]
    runtime_service: AgentRuntimeService | None = None
    turn_factory: Callable[[TurnRuntimeContext, IncomingMessage, str, SessionRecord], BackendTurnSession] = BackendTurnSession

    async def run(self, message: IncomingMessage, execution_key: str, session: SessionRecord) -> None:
        if not self.supports_backend(session.backend):
            await self.reply(message, f"Unsupported backend: {session.backend}")
            return

        turn = self.turn_factory(self.runtime_context, message, execution_key, session)
        await turn.run(self.message_summary_text(message), self.build_backend_prompt(message))

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
