from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from openrelay.agent_runtime import ApprovalDecision, ApprovalRequest, RunningTurnHandle, RuntimeEventSink

from .mapper import CodexProtocolMapper, CodexTurnState
from .transport import CodexRpcTransport


@dataclass(slots=True)
class _PendingApproval:
    request: ApprovalRequest
    future: asyncio.Future[dict[str, Any]]


@dataclass(slots=True)
class _CodexRuntimeTurnHandle:
    session_id: str
    turn_id: str
    backend: str
    future: asyncio.Future[None]

    async def wait(self) -> None:
        await self.future


class CodexTurnStream:
    def __init__(
        self,
        *,
        session_id: str,
        native_session_id: str,
        sink: RuntimeEventSink,
        mapper: CodexProtocolMapper,
        transport: CodexRpcTransport,
    ) -> None:
        self.session_id = session_id
        self.native_session_id = native_session_id
        self.turn_id = mapper.turn_id
        self.sink = sink
        self.mapper = mapper
        self.transport = transport
        self.state = CodexTurnState()
        self.pending_approvals: dict[str, _PendingApproval] = {}
        self.future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.done = False
        self.interrupt_message = "interrupted by /stop"
        self.interrupt_sent = False
        self.interrupted = False

    async def bind_started_turn(self, turn_id: str) -> None:
        self.turn_id = turn_id or self.turn_id
        self.mapper.turn_id = self.turn_id
        if self.interrupted and self.turn_id and not self.interrupt_sent:
            self.interrupt_sent = True
            try:
                await self.transport.request(
                    "turn/interrupt",
                    {"threadId": self.native_session_id, "turnId": self.turn_id},
                )
            except Exception:
                return

    async def handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if self.done:
            return
        events = self.mapper.map_notification(method, params, self.state)
        self.turn_id = self.mapper.turn_id or self.turn_id
        terminal_error: BaseException | None = None
        try:
            for event in events:
                await self.sink.publish(event)
                if event.turn_id:
                    self.turn_id = event.turn_id
                    self.mapper.turn_id = self.turn_id
                if event.event_type == "turn.completed":
                    self.done = True
                    if not self.future.done():
                        self.future.set_result(None)
                elif event.event_type == "turn.interrupted":
                    self.done = True
                    terminal_error = InterruptedError(getattr(event, "message", self.interrupt_message))
                elif event.event_type == "turn.failed":
                    self.done = True
                    terminal_error = RuntimeError(getattr(event, "message", "turn failed"))
        except BaseException as exc:
            self.done = True
            terminal_error = exc
        if terminal_error is not None and not self.future.done():
            self.future.set_exception(terminal_error)

    async def handle_server_request(
        self,
        request_id: int | str,
        method: str,
        params: dict[str, Any],
    ) -> bool:
        if self.done:
            return False
        requested = self.mapper.map_server_request(request_id, method, params)
        if requested is None:
            return False
        pending = _PendingApproval(
            request=requested.request,
            future=asyncio.get_running_loop().create_future(),
        )
        self.pending_approvals[pending.request.approval_id] = pending
        await self.sink.publish(requested)
        try:
            result = await pending.future
        finally:
            self.pending_approvals.pop(requested.request.approval_id, None)
        await self.transport.send_result(request_id, result)
        return True

    async def resolve_approval(
        self,
        request: ApprovalRequest,
        decision: ApprovalDecision,
    ) -> None:
        pending = self.pending_approvals.get(request.approval_id)
        if pending is None:
            raise KeyError(f"Unknown approval request: {request.approval_id}")
        response = self.mapper.build_approval_response(request, decision)
        if not pending.future.done():
            pending.future.set_result(response)

    async def interrupt(self, transport: CodexRpcTransport | None = None) -> None:
        self.interrupted = True
        if self.turn_id and self.interrupt_sent:
            return
        self.interrupt_message = "interrupted by /stop"
        target_transport = transport or self.transport
        if not self.turn_id:
            return
        self.interrupt_sent = True
        try:
            await target_transport.request(
                "turn/interrupt",
                {"threadId": self.native_session_id, "turnId": self.turn_id},
            )
        except Exception:
            return

    def build_handle(self) -> RunningTurnHandle:
        return _CodexRuntimeTurnHandle(
            session_id=self.session_id,
            turn_id=self.turn_id,
            backend="codex",
            future=self.future,
        )
