from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from openrelay.core import AppConfig, IncomingMessage, SessionRecord
from openrelay.observability import MessageTraceContext, MessageTraceRecorder
from openrelay.storage import StateStore

from .dispatch_models import DispatchDecision
from .execution import ExecutionInput, RuntimeExecutionCoordinator
from .follow_up import QueuedFollowUp
from .message_dispatch import MessageDispatchService

NON_BLOCKING_ACTIVE_RUN_COMMANDS = {"/ping", "/status", "/usage", "/help", "/tools", "/restart", "/compact"}

LOGGER = logging.getLogger("openrelay.runtime")


@dataclass(slots=True)
class RuntimeMessageApplicationService:
    config: AppConfig
    store: StateStore
    execution_coordinator: RuntimeExecutionCoordinator
    message_dispatch: MessageDispatchService
    is_allowed_user: Callable[[str], bool]
    trace_recorder: MessageTraceRecorder
    reply: Callable[..., Awaitable[None]]
    handle_command: Callable[[IncomingMessage, str, SessionRecord], Awaitable[bool]]
    run_backend_turn: Callable[..., Awaitable[None]]
    log_dispatch_resolution: Callable[[IncomingMessage, str, SessionRecord, str], None]

    async def handle(self, message: IncomingMessage) -> None:
        message, trace_context = self.trace_recorder.bind_message(message)
        try:
            self.trace_recorder.record(
                trace_context,
                stage="ingress",
                event_type="ingress.message.received",
                summary=self._message_summary_text(message) or "[empty message]",
                payload={
                    "actionable": message.actionable,
                    "chat_type": message.chat_type,
                    "has_local_images": bool(message.local_image_paths),
                    "has_remote_images": bool(message.remote_image_keys),
                },
            )
            ignore_reason = self._ignore_reason(message)
            if ignore_reason:
                self.trace_recorder.record(
                    trace_context,
                    stage="ingress",
                    event_type="ingress.message.ignored",
                    summary=ignore_reason,
                    payload={"reason": ignore_reason},
                )
                return
            if not self.is_allowed_user(message.sender_open_id):
                self.trace_recorder.record(
                    trace_context,
                    stage="dispatch",
                    event_type="dispatch.turn.rejected",
                    level="warning",
                    summary="unauthorized sender",
                    payload={"sender_open_id": message.sender_open_id},
                )
                await self.reply(
                    message,
                    "你没有权限使用 openrelay。",
                    command_reply=True,
                    command_name="",
                    trace_context=trace_context,
                )
                return

            decision = self.message_dispatch.resolve_and_decide(message)
            resolved = decision.resolved
            trace_context = self.trace_recorder.enrich_context(
                trace_context,
                relay_session_id=resolved.session.session_id,
                session_key=resolved.session_key,
                execution_key=decision.execution_key,
                backend=resolved.session.backend,
                native_session_id=resolved.session.native_session_id,
            )
            self._record_resolution(decision, trace_context)
            self.log_dispatch_resolution(message, resolved.session_key, resolved.session, "dispatch")
            if decision.kind == "stop":
                await self.handle_stop(message, decision.execution_key, trace_context=trace_context)
                return
            await self._handle_dispatch_decision(decision, trace_context)
        except Exception:
            self.trace_recorder.record(
                trace_context,
                stage="error",
                event_type="dispatch.failed",
                level="error",
                summary=f"dispatch failed for {message.event_id}",
            )
            LOGGER.exception("dispatch_message failed for event_id=%s chat_id=%s", message.event_id, message.chat_id)

    async def handle_stop(
        self,
        message: IncomingMessage,
        execution_key: str,
        *,
        trace_context: MessageTraceContext | None = None,
    ) -> None:
        active = self.execution_coordinator.active_run(execution_key)
        if active is None:
            await self.reply(
                message,
                "当前没有进行中的回复。",
                command_reply=True,
                command_name="",
                trace_context=trace_context,
            )
            return
        await active.cancel("interrupted by /stop")
        queued_follow_up_count = self.execution_coordinator.queued_follow_up_count(execution_key)
        stop_message = "已发送停止请求，正在中断当前回复。"
        if queued_follow_up_count > 0:
            stop_message = f"{stop_message[:-1]} 停止后会继续处理已收到的 {queued_follow_up_count} 条补充消息。"
        await self.reply(
            message,
            stop_message,
            command_reply=True,
            command_name="",
            trace_context=trace_context,
        )

    async def cancel_active_run_for_session(self, session: SessionRecord, command_name: str) -> bool:
        execution_key = self.message_dispatch.build_execution_key(session.base_key, session)
        active = self.execution_coordinator.active_run(execution_key)
        if active is None:
            return False
        await active.cancel(f"interrupted by {command_name}")
        return True

    async def _handle_dispatch_decision(self, decision: DispatchDecision, trace_context: MessageTraceContext) -> None:
        message = decision.resolved.message
        execution_key = decision.execution_key
        if self.execution_coordinator.is_locked(execution_key) and self._should_bypass_active_run(message.text):
            handled = await self.handle_command(message, decision.resolved.session_key, decision.resolved.session)
            if handled:
                return
        if self.execution_coordinator.is_locked(execution_key) and await self.execution_coordinator.try_handle_live_input(
            execution_key, message
        ):
            return
        if self.execution_coordinator.is_locked(execution_key):
            queued_follow_up = self.execution_coordinator.enqueue_pending_input(execution_key, message)
            if queued_follow_up is not None:
                self.trace_recorder.record(
                    trace_context,
                    stage="queue",
                    event_type="queue.follow_up.enqueued",
                    summary=queued_follow_up.acknowledgement_text(),
                )
                await self.reply(message, queued_follow_up.acknowledgement_text(), trace_context=trace_context)
            return
        async with self.execution_coordinator.lock_for(execution_key):
            await self._handle_serialized_inputs(decision, execution_key, trace_context)

    async def _handle_serialized_inputs(
        self,
        initial_input: ExecutionInput,
        execution_key: str,
        trace_context: MessageTraceContext,
    ) -> None:
        pending_input: ExecutionInput | None = initial_input
        while pending_input is not None:
            await self._handle_single_input(pending_input, execution_key, trace_context)
            pending_input = self.execution_coordinator.dequeue_pending_input(execution_key)

    async def _handle_single_input(
        self,
        pending_input: ExecutionInput,
        execution_key: str,
        trace_context: MessageTraceContext,
    ) -> None:
        if isinstance(pending_input, DispatchDecision):
            decision = pending_input
            message = decision.resolved.message
        else:
            message = pending_input.to_message() if isinstance(pending_input, QueuedFollowUp) else pending_input
            decision = self.message_dispatch.resolve_and_decide(message)
            self.log_dispatch_resolution(message, decision.resolved.session_key, decision.resolved.session, "serialized input")
            trace_context = self.trace_recorder.enrich_context(
                trace_context,
                relay_session_id=decision.resolved.session.session_id,
                session_key=decision.resolved.session_key,
                execution_key=execution_key,
                backend=decision.resolved.session.backend,
            )
            self.trace_recorder.record(
                trace_context,
                stage="queue",
                event_type="queue.follow_up.dequeued",
                summary=self._message_summary_text(message) or "[queued input]",
            )
        session_key = decision.resolved.session_key
        session = decision.resolved.session
        if message.text.startswith("/"):
            handled = await self.handle_command(message, session_key, session)
            if handled:
                return
        await self.run_backend_turn(message, execution_key, session, trace_context=trace_context)

    def _ignore_reason(self, message: IncomingMessage) -> str:
        if not self._message_summary_text(message):
            return "empty message"
        if self.config.feishu.bot_open_id and message.sender_open_id == self.config.feishu.bot_open_id:
            return "self message"
        if self.store.remember_message(message.event_id or message.message_id):
            return "duplicate message"
        if not message.actionable:
            return "non actionable message"
        return ""

    def _message_summary_text(self, message: IncomingMessage) -> str:
        text = str(message.text or "").strip()
        if text:
            return text
        if message.local_image_paths:
            count = len(message.local_image_paths)
            return "[图片]" if count == 1 else f"[图片 x{count}]"
        return ""

    def _should_bypass_active_run(self, text: str) -> bool:
        stripped = str(text or "").strip()
        if not stripped.startswith("/"):
            return False
        command = stripped.split(maxsplit=1)[0].lower()
        if command in NON_BLOCKING_ACTIVE_RUN_COMMANDS:
            return True
        if command != "/resume":
            return False
        tokens = stripped.split(maxsplit=2)
        return len(tokens) == 1

    def _record_resolution(self, decision: DispatchDecision, trace_context: MessageTraceContext) -> None:
        resolved = decision.resolved
        self.trace_recorder.record(
            trace_context,
            stage="session",
            event_type="session.key.resolved",
            summary=resolved.session_key,
            payload={
                "is_top_level_control_command": resolved.is_top_level_control_command,
                "is_top_level_message": resolved.is_top_level_message,
                "control_key": resolved.control_key,
            },
        )
        self.trace_recorder.record(
            trace_context,
            stage="session",
            event_type="session.loaded",
            summary=resolved.session.session_id,
            payload={
                "backend": resolved.session.backend,
                "cwd": resolved.session.cwd,
                "native_session_id": resolved.session.native_session_id,
            },
        )
        if decision.kind == "command":
            event_type = "dispatch.command.detected"
            summary = decision.command_name or "command"
        elif decision.kind == "turn":
            event_type = "dispatch.turn.accepted"
            summary = self._message_summary_text(resolved.message) or "turn accepted"
        elif decision.kind == "stop":
            event_type = "dispatch.command.detected"
            summary = decision.command_name or "/stop"
        else:
            event_type = "dispatch.turn.rejected"
            summary = decision.kind
        self.trace_recorder.record(trace_context, stage="dispatch", event_type=event_type, summary=summary)
