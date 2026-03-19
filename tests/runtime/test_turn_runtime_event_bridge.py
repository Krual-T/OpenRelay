from __future__ import annotations

from types import SimpleNamespace

import pytest

from openrelay.agent_runtime import ApprovalDecision, ApprovalRequestedEvent, SessionStartedEvent
from openrelay.agent_runtime.models import ApprovalRequest
from openrelay.runtime.turn_runtime_event_bridge import TurnRuntimeEventBridge


class _Controller:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def update_trace_context(self, **changes: str) -> None:
        self.calls.append(("update_trace_context", changes))

    async def attach_native_session(self, native_session_id: str) -> None:
        self.calls.append(("attach_native_session", native_session_id))

    def apply_runtime_snapshot(self, state: object) -> None:
        self.calls.append(("apply_runtime_snapshot", state))

    def mark_assistant_delta_received(self) -> None:
        self.calls.append(("mark_assistant_delta_received", None))

    async def resolve_approval_request(self, request: ApprovalRequest) -> ApprovalDecision:
        self.calls.append(("resolve_approval_request", request))
        return ApprovalDecision(decision="approve")

    def apply_approval_resolution(self, request: ApprovalRequest, decision: ApprovalDecision) -> None:
        self.calls.append(("apply_approval_resolution", (request, decision)))

    def request_streaming_update(self) -> None:
        self.calls.append(("request_streaming_update", None))


@pytest.mark.asyncio
async def test_turn_runtime_event_bridge_delegates_state_mutation_to_controller() -> None:
    request = ApprovalRequest(
        approval_id="approval_1",
        session_id="relay_1",
        turn_id="turn_1",
        kind="command",
        title="Approve command",
        description="Run command",
        payload={"command": "echo hi"},
    )
    event = ApprovalRequestedEvent(
        event_type="approval.requested",
        session_id="relay_1",
        turn_id="turn_1",
        backend="codex",
        request=request,
    )
    binding = SimpleNamespace(relay_session_id="relay_1")
    runtime_service = SimpleNamespace(
        turn_registry=SimpleNamespace(read=lambda session_id, turn_id: None),
        resolve_approval=lambda binding, request, decision: None,
    )
    resolved: list[tuple[object, object, object]] = []

    async def resolve_approval(binding: object, request: object, decision: object) -> None:
        resolved.append((binding, request, decision))

    runtime_service.resolve_approval = resolve_approval
    controller = _Controller()
    bridge = TurnRuntimeEventBridge(
        runtime=SimpleNamespace(runtime_service=runtime_service, session_ux=SimpleNamespace(format_cwd=lambda cwd, session=None: cwd)),
        controller=controller,
        presenter=SimpleNamespace(),
    )

    await bridge.handle_runtime_event(binding, event)

    assert controller.calls[0] == (
        "update_trace_context",
        {"relay_session_id": "relay_1", "backend": "codex", "turn_id": "turn_1"},
    )
    assert ("resolve_approval_request", request) in controller.calls
    assert any(name == "apply_approval_resolution" for name, _ in controller.calls)
    assert controller.calls[-1] == ("request_streaming_update", None)
    assert resolved == [(binding, request, ApprovalDecision(decision="approve"))]


@pytest.mark.asyncio
async def test_turn_runtime_event_bridge_attaches_native_session_through_controller() -> None:
    event = SessionStartedEvent(
        event_type="session.started",
        session_id="relay_1",
        turn_id="turn_1",
        backend="codex",
        native_session_id="native_1",
    )
    runtime_state = SimpleNamespace(plan_steps=[])
    runtime_service = SimpleNamespace(
        turn_registry=SimpleNamespace(read=lambda session_id, turn_id: runtime_state),
    )
    controller = _Controller()
    bridge = TurnRuntimeEventBridge(
        runtime=SimpleNamespace(runtime_service=runtime_service, session_ux=SimpleNamespace(format_cwd=lambda cwd, session=None: cwd)),
        controller=controller,
        presenter=SimpleNamespace(),
    )

    await bridge.handle_runtime_event(SimpleNamespace(relay_session_id="relay_1"), event)

    assert ("attach_native_session", "native_1") in controller.calls
    assert ("apply_runtime_snapshot", runtime_state) in controller.calls
