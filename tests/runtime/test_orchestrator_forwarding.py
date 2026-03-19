from __future__ import annotations

import pytest

from openrelay.core import IncomingMessage, SessionRecord
from openrelay.runtime.orchestrator import RuntimeOrchestrator


class _FakeMessageApplication:
    def __init__(self) -> None:
        self.handled: list[IncomingMessage] = []
        self.stopped: list[str] = []
        self.canceled: list[str] = []

    async def handle(self, message: IncomingMessage) -> None:
        self.handled.append(message)

    async def handle_stop(self, message: IncomingMessage, execution_key: str) -> None:
        self.stopped.append(execution_key)

    async def cancel_active_run_for_session(self, session: SessionRecord, command_name: str) -> bool:
        self.canceled.append(command_name)
        return True


class _FakeCommandRouter:
    def __init__(self) -> None:
        self.calls: list[tuple[IncomingMessage, str, SessionRecord]] = []

    async def handle(self, message: IncomingMessage, session_key: str, session: SessionRecord) -> bool:
        self.calls.append((message, session_key, session))
        return True


def _build_message() -> IncomingMessage:
    return IncomingMessage(
        event_id="evt",
        message_id="om",
        chat_id="oc",
        chat_type="p2p",
        sender_open_id="ou",
        text="hello",
        actionable=True,
    )


def _build_session() -> SessionRecord:
    return SessionRecord(
        session_id="session_1",
        base_key="p2p:oc_1",
        backend="codex",
        cwd="/tmp",
    )


@pytest.mark.asyncio
async def test_dispatch_message_forwards_to_message_application() -> None:
    orchestrator = object.__new__(RuntimeOrchestrator)
    stub = _FakeMessageApplication()
    orchestrator.message_application = stub
    message = _build_message()

    await orchestrator.dispatch_message(message)

    assert stub.handled and stub.handled[-1] is message


@pytest.mark.asyncio
async def test_handle_command_forwards_to_router() -> None:
    orchestrator = object.__new__(RuntimeOrchestrator)
    orchestrator.command_router = _FakeCommandRouter()
    message = _build_message()
    session = _build_session()

    result = await orchestrator._handle_command(message, session.base_key, session)

    assert result is True
    assert orchestrator.command_router.calls[0][0] is message


@pytest.mark.asyncio
async def test_handle_stop_and_cancel_delegate_to_message_application() -> None:
    orchestrator = object.__new__(RuntimeOrchestrator)
    stub = _FakeMessageApplication()
    orchestrator.message_application = stub
    message = _build_message()
    session = _build_session()

    await orchestrator._handle_stop(message, "execution:1")
    canceled = await orchestrator._cancel_active_run_for_session(session, "test-command")

    assert "execution:1" in stub.stopped
    assert canceled is True
    assert stub.canceled == ["test-command"]
