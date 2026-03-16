from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from openrelay.agent_runtime import (
    AssistantCompletedEvent,
    BackendCapabilities,
    RunningTurnHandle,
    RuntimeEventSink,
    SessionStartedEvent,
    SessionSummary,
    SessionTranscript,
    StartSessionRequest,
    TurnCompletedEvent,
    TurnFailedEvent,
    TurnInput,
    TurnInterruptedEvent,
    TurnStartedEvent,
)
from openrelay.agent_runtime.models import SessionLocator
from openrelay.core import utc_now

from .mapper import ClaudeResponseMapper
from .transport import ClaudeCliTransport


@dataclass(slots=True)
class ClaudeCompletedHandle(RunningTurnHandle):
    session_id: str
    turn_id: str
    backend: str
    future: asyncio.Task[None]

    async def wait(self) -> None:
        await self.future


class ClaudeSessionClient:
    def __init__(
        self,
        *,
        transport: ClaudeCliTransport,
        default_model: str,
        mapper: ClaudeResponseMapper,
    ) -> None:
        self.transport = transport
        self.default_model = default_model
        self.mapper = mapper
        self.capability_snapshot = BackendCapabilities()

    async def start_session(self, request: StartSessionRequest) -> SessionSummary:
        session_id = self._new_session_id()
        return SessionSummary(
            backend="claude",
            native_session_id=session_id,
            title="Claude session",
            preview="",
            cwd=request.cwd,
            updated_at=utc_now(),
            status="idle",
        )

    async def resume_session(self, locator: SessionLocator) -> SessionSummary:
        return SessionSummary(
            backend="claude",
            native_session_id=locator.native_session_id,
            title=locator.native_session_id or "Claude session",
            preview="",
            cwd="",
            updated_at=utc_now(),
            status="idle",
        )

    async def list_sessions(self, _request) -> tuple[list[SessionSummary], str]:
        raise NotImplementedError("Claude runtime backend does not support session listing")

    async def read_session(self, _locator: SessionLocator) -> SessionTranscript:
        raise NotImplementedError("Claude runtime backend does not support transcript reading")

    async def start_turn(
        self,
        locator: SessionLocator,
        turn_input: TurnInput,
        sink: RuntimeEventSink,
        session_id: str,
    ) -> RunningTurnHandle:
        turn_id = uuid4().hex
        native_session_id = locator.native_session_id or self._new_session_id()

        async def run_turn() -> None:
            await sink.publish(
                TurnStartedEvent(
                    backend="claude",
                    session_id=session_id,
                    turn_id=turn_id,
                    event_type="turn.started",
                )
            )
            if not locator.native_session_id:
                await sink.publish(
                    SessionStartedEvent(
                        backend="claude",
                        session_id=session_id,
                        turn_id=turn_id,
                        event_type="session.started",
                        native_session_id=native_session_id,
                        title="Claude session",
                    )
                )
            try:
                result = await self.transport.run(
                    prompt=turn_input.text,
                    cwd=turn_input.cwd or str(self.transport.workspace_root),
                    model=turn_input.model or self.default_model,
                    safety_mode=turn_input.safety_mode,
                    session_id=locator.native_session_id,
                )
                if not result.stdout:
                    raise RuntimeError(result.stderr or "Claude runtime backend returned no output")
                reply = self.mapper.parse(result.stdout)
                if reply.text:
                    await sink.publish(
                        AssistantCompletedEvent(
                            backend="claude",
                            session_id=session_id,
                            turn_id=turn_id,
                            event_type="assistant.completed",
                            text=reply.text,
                        )
                    )
                await sink.publish(
                    TurnCompletedEvent(
                        backend="claude",
                        session_id=session_id,
                        turn_id=turn_id,
                        event_type="turn.completed",
                        final_text=reply.text,
                    )
                )
            except Exception as exc:
                message = str(exc)
                event_cls = TurnInterruptedEvent if "interrupted" in message.lower() else TurnFailedEvent
                await sink.publish(
                    event_cls(
                        backend="claude",
                        session_id=session_id,
                        turn_id=turn_id,
                        event_type="turn.interrupted" if event_cls is TurnInterruptedEvent else "turn.failed",
                        message=message,
                    )
                )
                raise

        return ClaudeCompletedHandle(
            session_id=session_id,
            turn_id=turn_id,
            backend="claude",
            future=asyncio.create_task(run_turn()),
        )

    async def interrupt_turn(self, _locator: SessionLocator, _turn_id: str) -> None:
        raise NotImplementedError("Claude runtime backend does not support turn interruption")

    async def resolve_approval(self, _locator: SessionLocator, _approval, _request) -> None:
        raise NotImplementedError("Claude runtime backend does not support approvals")

    async def compact_session(self, _locator: SessionLocator) -> dict[str, object]:
        raise NotImplementedError("Claude runtime backend does not support session compact")

    async def shutdown(self) -> None:
        return None

    def _new_session_id(self) -> str:
        return f"claude_{uuid4().hex[:12]}"
