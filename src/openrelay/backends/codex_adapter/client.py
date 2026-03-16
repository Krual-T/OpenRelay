from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from openrelay.agent_runtime import (
    ApprovalDecision,
    ApprovalRequest,
    ListSessionsRequest,
    RunningTurnHandle,
    RuntimeEventSink,
    SessionLocator,
    SessionSummary,
    SessionTranscript,
    StartSessionRequest,
    TurnInput,
)
from openrelay.agent_runtime.events import SessionStartedEvent
from openrelay.agent_runtime.models import TranscriptMessage

from .mapper import CodexProtocolMapper
from .transport import CodexRpcTransport
from .turn_stream import CodexTurnStream


def _thread_summary_to_session(summary: Any) -> SessionSummary:
    return SessionSummary(
        backend="codex",
        native_session_id=summary.thread_id,
        title=summary.name or summary.preview or summary.thread_id,
        preview=summary.preview,
        cwd=summary.cwd,
        updated_at=summary.updated_at,
        status=summary.status,
    )


def _thread_details_to_transcript(details: Any) -> SessionTranscript:
    messages = tuple(
        TranscriptMessage(role=message.role, text=message.text)
        for message in details.messages
    )
    return SessionTranscript(
        summary=SessionSummary(
            backend="codex",
            native_session_id=details.thread_id,
            title=details.name or details.preview or details.thread_id,
            preview=details.preview,
            cwd=details.cwd,
            updated_at=details.updated_at,
            status=details.status,
        ),
        messages=messages,
    )


class CodexSessionClient:
    def __init__(
        self,
        *,
        transport: CodexRpcTransport,
        default_model: str,
        mapper_factory: Callable[..., CodexProtocolMapper] = CodexProtocolMapper,
    ) -> None:
        self.transport = transport
        self.default_model = default_model
        self.mapper_factory = mapper_factory
        self.active_turns: dict[tuple[str, str], CodexTurnStream] = {}

    async def start_session(self, request: StartSessionRequest) -> SessionSummary:
        mapper = self.mapper_factory(session_id="", native_session_id="")
        result = await self.transport.request(
            "thread/start",
            mapper.build_thread_params(
                cwd=request.cwd,
                model=request.model,
                safety_mode=request.safety_mode,
                default_model=self.default_model,
            ),
        )
        thread = result.get("thread") if isinstance(result, dict) and isinstance(result.get("thread"), dict) else {}
        thread_id = str(thread.get("id") or "")
        return SessionSummary(
            backend="codex",
            native_session_id=thread_id,
            title=str(thread.get("name") or thread.get("preview") or thread_id),
            preview=str(thread.get("preview") or ""),
            cwd=request.cwd,
            updated_at=str(thread.get("updatedAt") or ""),
            status=str(thread.get("status") or ""),
        )

    async def resume_session(self, locator: SessionLocator) -> SessionSummary:
        return (await self.read_session(locator)).summary

    async def list_sessions(self, request: ListSessionsRequest) -> tuple[list[SessionSummary], str]:
        summaries, cursor = await self.transport.list_threads(limit=request.limit)
        return ([_thread_summary_to_session(summary) for summary in summaries], cursor)

    async def read_session(self, locator: SessionLocator) -> SessionTranscript:
        details = await self.transport.read_thread(locator.native_session_id, include_turns=True)
        return _thread_details_to_transcript(details)

    async def start_turn(
        self,
        locator: SessionLocator,
        turn_input: TurnInput,
        sink: RuntimeEventSink,
        session_id: str,
    ) -> RunningTurnHandle:
        mapper = self.mapper_factory(session_id=session_id, native_session_id=locator.native_session_id)
        thread_id = await self._ensure_thread(locator, turn_input, sink, session_id, mapper)
        mapper.native_session_id = thread_id
        stream = CodexTurnStream(
            session_id=session_id,
            native_session_id=thread_id,
            sink=sink,
            mapper=mapper,
            transport=self.transport,
        )

        async def notify_handler(method: str, params: dict[str, Any]) -> None:
            await stream.handle_notification(method, params)
            if stream.turn_id:
                self.active_turns[(thread_id, stream.turn_id)] = stream

        async def server_handler(
            request_id: int | str,
            method: str,
            params: dict[str, Any],
        ) -> bool:
            return await stream.handle_server_request(request_id, method, params)

        self.transport.subscribe_notifications(notify_handler)
        self.transport.subscribe_server_requests(server_handler)
        handle = stream.build_handle()

        async def drive() -> None:
            try:
                result = await self.transport.request(
                    "turn/start",
                    mapper.build_turn_start_params(
                        thread_id=thread_id,
                        turn_input=turn_input,
                    ),
                )
                turn_id = str(result.get("turn", {}).get("id") or "")
                await stream.bind_started_turn(turn_id)
                if stream.turn_id:
                    self.active_turns[(thread_id, stream.turn_id)] = stream
                handle.turn_id = stream.turn_id
            except BaseException as exc:
                stream.done = True
                if not stream.future.done():
                    stream.future.set_exception(exc)

        self.active_turns[(thread_id, "")] = stream

        def _cleanup(_future: asyncio.Future[None]) -> None:
            self.transport.unsubscribe_notifications(notify_handler)
            self.transport.unsubscribe_server_requests(server_handler)
            self.active_turns.pop((thread_id, ""), None)
            if stream.turn_id:
                self.active_turns.pop((thread_id, stream.turn_id), None)

        stream.future.add_done_callback(_cleanup)
        asyncio.create_task(drive())
        return handle

    async def interrupt_turn(self, locator: SessionLocator, turn_id: str) -> None:
        stream = self.active_turns.get((locator.native_session_id, turn_id))
        if stream is not None:
            await stream.interrupt(self.transport)
            return
        await self.transport.request(
            "turn/interrupt",
            {"threadId": locator.native_session_id, "turnId": turn_id},
        )

    async def resolve_approval(
        self,
        locator: SessionLocator,
        approval: ApprovalDecision,
        request: ApprovalRequest,
    ) -> None:
        stream = self.active_turns.get((locator.native_session_id, request.turn_id))
        if stream is None:
            for (thread_id, _turn_id), candidate in self.active_turns.items():
                if thread_id == locator.native_session_id and request.approval_id in candidate.pending_approvals:
                    stream = candidate
                    break
        if stream is None:
            raise KeyError(f"Unknown approval request: {request.approval_id}")
        await stream.resolve_approval(request, approval)

    async def compact_session(self, locator: SessionLocator) -> dict[str, Any]:
        return await self.transport.compact_thread(locator.native_session_id)

    async def shutdown(self) -> None:
        await self.transport.stop()

    async def _ensure_thread(
        self,
        locator: SessionLocator,
        turn_input: TurnInput,
        sink: RuntimeEventSink,
        session_id: str,
        mapper: CodexProtocolMapper,
    ) -> str:
        if locator.native_session_id:
            await self.transport.request(
                "thread/resume",
                {
                    **mapper.build_thread_params(
                        cwd=turn_input.cwd,
                        model=turn_input.model,
                        safety_mode=turn_input.safety_mode,
                        default_model=self.default_model,
                    ),
                    "threadId": locator.native_session_id,
                },
            )
            return locator.native_session_id
        result = await self.transport.request(
            "thread/start",
            mapper.build_thread_params(
                cwd=turn_input.cwd,
                model=turn_input.model,
                safety_mode=turn_input.safety_mode,
                default_model=self.default_model,
            ),
        )
        thread = result.get("thread") if isinstance(result, dict) and isinstance(result.get("thread"), dict) else {}
        thread_id = str(thread.get("id") or "")
        if not thread_id:
            raise RuntimeError("Codex app-server returned no thread id")
        await sink.publish(
            SessionStartedEvent(
                backend="codex",
                session_id=session_id,
                turn_id="",
                event_type="session.started",
                native_session_id=thread_id,
                title=str(thread.get("name") or thread.get("preview") or ""),
                provider_payload={"native_session_id": thread_id},
            )
        )
        return thread_id
