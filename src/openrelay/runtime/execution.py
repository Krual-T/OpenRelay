from __future__ import annotations

import asyncio
from collections import defaultdict, deque

from openrelay.core import ActiveRun, IncomingMessage

from .follow_up import QueuedFollowUp


ExecutionInput = IncomingMessage | QueuedFollowUp


class RuntimeExecutionCoordinator:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._pending_inputs: dict[str, deque[ExecutionInput]] = defaultdict(deque)
        self.active_runs: dict[str, ActiveRun] = {}

    def is_locked(self, execution_key: str) -> bool:
        return self._locks[execution_key].locked()

    def lock_for(self, execution_key: str) -> asyncio.Lock:
        return self._locks[execution_key]

    def active_run(self, execution_key: str) -> ActiveRun | None:
        return self.active_runs.get(execution_key)

    def start_run(self, execution_key: str, run: ActiveRun) -> None:
        self.active_runs[execution_key] = run

    def finish_run(self, execution_key: str) -> None:
        self.active_runs.pop(execution_key, None)

    async def try_handle_live_input(self, execution_key: str, message: IncomingMessage) -> bool:
        active = self.active_run(execution_key)
        if active is None or active.try_handle_input is None:
            return False
        return await active.try_handle_input(message)

    def enqueue_pending_input(self, execution_key: str, message: IncomingMessage) -> QueuedFollowUp | None:
        pending_inputs = self._pending_inputs[execution_key]
        if self.active_run(execution_key) is not None and not message.text.startswith("/"):
            last_input = pending_inputs[-1] if pending_inputs else None
            if isinstance(last_input, QueuedFollowUp):
                last_input.merge(message)
                return last_input
            queued_follow_up = QueuedFollowUp.from_message(message)
            pending_inputs.append(queued_follow_up)
            return queued_follow_up
        pending_inputs.append(message)
        return None

    def dequeue_pending_input(self, execution_key: str) -> ExecutionInput | None:
        pending_inputs = self._pending_inputs.get(execution_key)
        if not pending_inputs:
            return None
        next_input = pending_inputs.popleft()
        if not pending_inputs:
            self._pending_inputs.pop(execution_key, None)
        return next_input

    def queued_follow_up_count(self, execution_key: str) -> int:
        pending_inputs = self._pending_inputs.get(execution_key)
        if not pending_inputs:
            return 0
        return sum(item.message_count for item in pending_inputs if isinstance(item, QueuedFollowUp))
