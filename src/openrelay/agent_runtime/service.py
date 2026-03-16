from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .backend import AgentBackend, ListSessionsRequest, RuntimeEventSink, StartSessionRequest
from .events import ApprovalRequestedEvent, RuntimeEvent, SessionStartedEvent
from .models import ApprovalDecision, ApprovalRequest, LiveTurnViewModel, SessionLocator, SessionSummary, SessionTranscript, TurnInput
from .reducer import LiveTurnRegistry
from openrelay.session.models import RelayScope, RelaySessionBinding
from openrelay.session.store import SessionBindingStore


class RuntimeEventSubscriber(Protocol):
    async def __call__(self, event: RuntimeEvent) -> None:
        raise NotImplementedError


class ApprovalTracker(Protocol):
    def remember(self, request: ApprovalRequest) -> None:
        raise NotImplementedError

    def resolve(self, approval_id: str) -> ApprovalRequest | None:
        raise NotImplementedError


class RuntimeEventHub:
    def __init__(self) -> None:
        self.subscribers: list[RuntimeEventSubscriber] = []

    def subscribe(self, subscriber: RuntimeEventSubscriber) -> None:
        self.subscribers.append(subscriber)

    async def publish(self, event: RuntimeEvent) -> None:
        for subscriber in self.subscribers:
            await subscriber(event)


@dataclass(slots=True)
class _HubSink(RuntimeEventSink):
    hub: RuntimeEventHub

    async def publish(self, event: RuntimeEvent) -> None:
        await self.hub.publish(event)


class AgentRuntimeService:
    def __init__(
        self,
        backends: dict[str, AgentBackend],
        bindings: SessionBindingStore,
        turn_registry: LiveTurnRegistry | None = None,
        event_hub: RuntimeEventHub | None = None,
        interaction_controller: ApprovalTracker | None = None,
    ) -> None:
        self.backends = backends
        self.bindings = bindings
        self.turn_registry = turn_registry or LiveTurnRegistry()
        self.event_hub = event_hub or RuntimeEventHub()
        self.interaction_controller = interaction_controller
        self.event_hub.subscribe(self._on_runtime_event)

    async def start_new_session(
        self,
        backend: str,
        request: StartSessionRequest,
        scope: RelayScope,
    ) -> RelaySessionBinding:
        adapter = self._select_backend(backend)
        summary = await adapter.start_session(request)
        binding = RelaySessionBinding(
            relay_session_id=scope.relay_session_id,
            backend=summary.backend,
            native_session_id=summary.native_session_id,
            cwd=request.cwd,
            model=request.model or "",
            safety_mode=request.safety_mode,
            feishu_chat_id=scope.feishu_chat_id,
            feishu_thread_id=scope.feishu_thread_id,
        )
        self.bindings.save(binding)
        await self.event_hub.publish(
            SessionStartedEvent(
                backend=summary.backend,
                session_id=binding.relay_session_id,
                turn_id="",
                event_type="session.started",
                native_session_id=summary.native_session_id,
                title=summary.title,
            )
        )
        return binding

    async def resume_session(self, locator: SessionLocator, scope: RelayScope) -> RelaySessionBinding:
        adapter = self._select_backend(locator.backend)
        summary = await adapter.resume_session(locator)
        binding = RelaySessionBinding(
            relay_session_id=scope.relay_session_id,
            backend=summary.backend,
            native_session_id=summary.native_session_id,
            cwd=summary.cwd,
            model="",
            safety_mode="workspace-write",
            feishu_chat_id=scope.feishu_chat_id,
            feishu_thread_id=scope.feishu_thread_id,
        )
        self.bindings.save(binding)
        return binding

    async def list_sessions(self, backend: str, request: ListSessionsRequest) -> tuple[list[SessionSummary], str]:
        return await self._select_backend(backend).list_sessions(request)

    async def read_session(self, locator: SessionLocator) -> SessionTranscript:
        return await self._select_backend(locator.backend).read_session(locator)

    async def run_turn(self, binding: RelaySessionBinding, turn_input: TurnInput) -> LiveTurnViewModel:
        sink = _HubSink(self.event_hub)
        adapter = self._select_backend(binding.backend)
        handle = await adapter.start_turn(binding.locator, turn_input, sink)
        await handle.wait()
        return self.turn_registry.read(binding.relay_session_id, handle.turn_id) or self.turn_registry.get_or_create(
            binding.relay_session_id,
            handle.turn_id,
            binding.backend,
            binding.native_session_id,
        ).state

    async def interrupt_turn(self, binding: RelaySessionBinding, turn_id: str) -> None:
        await self._select_backend(binding.backend).interrupt_turn(binding.locator, turn_id)

    async def resolve_approval(
        self,
        binding: RelaySessionBinding,
        request: ApprovalRequest,
        decision: ApprovalDecision,
    ) -> None:
        await self._select_backend(binding.backend).resolve_approval(binding.locator, decision, request)

    async def compact_session(self, binding: RelaySessionBinding) -> dict[str, object]:
        return await self._select_backend(binding.backend).compact_session(binding.locator)

    def _select_backend(self, backend: str) -> AgentBackend:
        adapter = self.backends.get(backend)
        if adapter is None:
            raise KeyError(f"Unknown backend: {backend}")
        return adapter

    async def _on_runtime_event(self, event: RuntimeEvent) -> None:
        state = self.turn_registry.apply(event)
        if isinstance(event, SessionStartedEvent) and event.native_session_id:
            self.bindings.update_native_session_id(event.session_id, event.native_session_id)
        if isinstance(event, ApprovalRequestedEvent) and self.interaction_controller is not None:
            self.interaction_controller.remember(event.request)
        if event.event_type == "approval.resolved" and self.interaction_controller is not None:
            approval_id = getattr(event, "approval_id", "")
            if approval_id:
                self.interaction_controller.resolve(approval_id)
        if not state.native_session_id:
            state.native_session_id = self.bindings.get(event.session_id).native_session_id if self.bindings.get(event.session_id) else ""
