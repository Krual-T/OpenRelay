from __future__ import annotations

from openrelay.core import IncomingMessage, SessionRecord


class RecordingMessageApplication:
    def __init__(self) -> None:
        self.handled: list[IncomingMessage] = []
        self.stopped: list[str] = []
        self.canceled: list[str] = []

    async def handle(self, message: IncomingMessage) -> None:
        self.handled.append(message)

    async def handle_stop(self, message: IncomingMessage, execution_key: str) -> None:
        _ = message
        self.stopped.append(execution_key)

    async def cancel_active_run_for_session(self, session: SessionRecord, command_name: str) -> bool:
        _ = session
        self.canceled.append(command_name)
        return True


class RecordingCommandRouter:
    def __init__(self) -> None:
        self.calls: list[tuple[IncomingMessage, str, SessionRecord]] = []

    async def handle(self, message: IncomingMessage, session_key: str, session: SessionRecord) -> bool:
        self.calls.append((message, session_key, session))
        return True
