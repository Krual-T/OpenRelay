from __future__ import annotations

import logging

from openrelay.agent_runtime import RuntimeEvent, TurnInput
from openrelay.core import BackendReply, IncomingMessage
from openrelay.session import RelaySessionBinding

from .turn import TurnBindingStore, TurnRuntimeContext
from .turn_run_controller import TurnRunController
from .turn_runtime_event_bridge import TurnRuntimeEventBridge

LOGGER = logging.getLogger("openrelay.runtime")


class TurnApplicationService:
    def __init__(
        self,
        runtime: TurnRuntimeContext,
        message: IncomingMessage,
        execution_key: str,
        controller: TurnRunController,
        event_bridge: TurnRuntimeEventBridge,
    ) -> None:
        self.runtime = runtime
        self.message = message
        self.execution_key = execution_key
        self.controller = controller
        self.event_bridge = event_bridge

    async def run(self, message_summary: str, backend_prompt: str) -> None:
        try:
            await self.controller.prepare(message_summary)
            self.controller.build_interaction_controller()
            self.runtime.execution_coordinator.start_run(self.execution_key, self.controller.activate_run(message_summary))
            reply = await self.run_with_agent_runtime(backend_prompt)
            self.controller.save_reply(reply)
            self.controller.record_event(
                stage="turn",
                event_type="turn.completed",
                summary=reply.text[:120],
                payload={"usage": reply.metadata.get("usage", {}) if isinstance(reply.metadata, dict) else {}},
            )
            await self.controller.reply_final(reply.text or "(empty reply)")
        except Exception as exc:
            if "interrupted by /stop" in str(exc).lower() or "interrupted" in str(exc).lower():
                self.controller.record_event(
                    stage="turn",
                    event_type="turn.interrupted",
                    summary=str(exc),
                    level="warning",
                )
                await self.controller.reply_final("已停止当前回复。")
            else:
                self.controller.record_event(
                    stage="turn",
                    event_type="turn.failed",
                    summary=str(exc),
                    level="error",
                )
                await self.controller.reply_final(f"处理失败：{exc}")
        finally:
            self.runtime.execution_coordinator.finish_run(self.execution_key)
            await self.controller.finalize()

    async def run_with_agent_runtime(self, backend_prompt: str) -> BackendReply:
        runtime_service = self.runtime.runtime_service
        binding_store = self.runtime.binding_store
        if runtime_service is None or binding_store is None:
            raise RuntimeError("agent runtime service is unavailable")
        binding = self._ensure_binding(binding_store)

        async def handle_runtime_event(event: RuntimeEvent) -> None:
            if event.session_id != self.controller.state.session.session_id:
                return
            await self.event_bridge.handle_runtime_event(binding, event)

        runtime_service.event_hub.subscribe(handle_runtime_event)
        try:
            state = await runtime_service.run_turn(
                binding,
                TurnInput(
                    text=backend_prompt,
                    local_image_paths=self.message.local_image_paths,
                    cwd=self.controller.state.session.cwd,
                    model=self.controller.state.session.model_override or None,
                    safety_mode=self.controller.state.session.safety_mode,
                ),
            )
        finally:
            runtime_service.event_hub.unsubscribe(handle_runtime_event)

        binding = binding_store.get(self.controller.state.session.session_id) or binding
        usage = None
        if state.usage is not None:
            usage = {
                "input_tokens": state.usage.input_tokens,
                "cached_input_tokens": state.usage.cached_input_tokens,
                "output_tokens": state.usage.output_tokens,
                "reasoning_output_tokens": state.usage.reasoning_output_tokens,
                "total_tokens": state.usage.total_tokens,
                "model_context_window": state.usage.context_window,
            }
        return BackendReply(
            text=state.assistant_text,
            native_session_id=binding.native_session_id,
            metadata={"usage": usage or {}},
        )

    def _ensure_binding(self, binding_store: TurnBindingStore) -> RelaySessionBinding:
        session = self.controller.state.session
        existing = binding_store.get(session.session_id)
        if existing is not None:
            return existing
        binding = RelaySessionBinding(
            relay_session_id=session.session_id,
            backend=session.backend,  # type: ignore[arg-type]
            native_session_id=session.native_session_id,
            cwd=session.cwd,
            model=session.model_override,
            safety_mode=session.safety_mode,
            feishu_chat_id=self.message.chat_id,
            feishu_thread_id=self.message.thread_id or self.message.root_id or "",
        )
        binding_store.save(binding)
        return binding
