from __future__ import annotations

import pytest

from openrelay.core import SessionRecord
from openrelay.runtime.orchestrator import RuntimeOrchestrator
from tests.support.app import make_incoming_message
from tests.support.runtime_orchestrator import RecordingCommandRouter, RecordingMessageApplication


def build_message():
    return make_incoming_message("hello", event_suffix="orchestrator", sender_open_id="ou")


def build_session() -> SessionRecord:
    return SessionRecord(
        session_id="session_1",
        base_key="p2p:oc_1",
        backend="codex",
        cwd="/tmp",
    )


@pytest.mark.asyncio
async def test_dispatch_message_forwards_to_message_application() -> None:
    orchestrator = object.__new__(RuntimeOrchestrator)
    stub = RecordingMessageApplication()
    orchestrator.message_application = stub
    message = build_message()

    await orchestrator.dispatch_message(message)

    assert stub.handled and stub.handled[-1] is message


@pytest.mark.asyncio
async def test_handle_command_forwards_to_router() -> None:
    orchestrator = object.__new__(RuntimeOrchestrator)
    orchestrator.command_router = RecordingCommandRouter()
    message = build_message()
    session = build_session()

    result = await orchestrator._handle_command(message, session.base_key, session)

    assert result is True
    assert orchestrator.command_router.calls[0][0] is message


@pytest.mark.asyncio
async def test_handle_stop_and_cancel_delegate_to_message_application() -> None:
    orchestrator = object.__new__(RuntimeOrchestrator)
    stub = RecordingMessageApplication()
    orchestrator.message_application = stub
    message = build_message()
    session = build_session()

    await orchestrator._handle_stop(message, "execution:1")
    canceled = await orchestrator._cancel_active_run_for_session(session, "test-command")

    assert "execution:1" in stub.stopped
    assert canceled is True
    assert stub.canceled == ["test-command"]
