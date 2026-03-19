from __future__ import annotations

import logging

from openrelay.agent_runtime import ApprovalRequestedEvent, AssistantDeltaEvent, RuntimeEvent, SessionStartedEvent
from openrelay.presentation.live_turn import LiveTurnPresenter
from openrelay.session import RelaySessionBinding

from .turn import TurnRuntimeContext
from .turn_run_controller import TurnRunController


LOGGER = logging.getLogger("openrelay.runtime")


class TurnRuntimeEventBridge:
    def __init__(
        self,
        runtime: TurnRuntimeContext,
        controller: TurnRunController,
        presenter: LiveTurnPresenter,
    ) -> None:
        self.runtime = runtime
        self.controller = controller
        self.presenter = presenter

    async def handle_runtime_event(self, binding: RelaySessionBinding, event: RuntimeEvent) -> None:
        runtime_service = self.runtime.runtime_service
        if runtime_service is None:
            return
        self.controller.update_trace_context(
            relay_session_id=binding.relay_session_id,
            backend=event.backend,
            turn_id=event.turn_id,
        )
        state = runtime_service.turn_registry.read(event.session_id, event.turn_id) if event.turn_id else None
        if isinstance(event, SessionStartedEvent):
            await self.controller.attach_native_session(event.native_session_id)
        if state is not None:
            self.controller.apply_runtime_snapshot(state)
            if event.event_type == "plan.updated" or state.plan_steps:
                LOGGER.info(
                    "runtime live state updated event_type=%s session_id=%s turn_id=%s plan_steps=%s",
                    event.event_type,
                    event.session_id,
                    event.turn_id,
                    [{"step": step.step, "status": step.status} for step in state.plan_steps],
                )
        if isinstance(event, AssistantDeltaEvent) and state is not None:
            self.controller.mark_assistant_delta_received()
        if isinstance(event, ApprovalRequestedEvent):
            decision = await self.controller.resolve_approval_request(event.request)
            await runtime_service.resolve_approval(binding, event.request, decision)
            self.controller.apply_approval_resolution(event.request, decision)
        self.controller.request_streaming_update()
