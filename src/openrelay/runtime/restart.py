from __future__ import annotations

import asyncio
import logging
import os
from typing import Awaitable


DEFAULT_SYSTEMD_SERVICE_UNIT = "openrelay.service"


def get_systemd_service_unit(env: dict[str, str] | None = None) -> str:
    current_env = os.environ if env is None else env
    raw_unit = (current_env.get("OPENRELAY_SYSTEMD_UNIT") or "").strip()
    return raw_unit or DEFAULT_SYSTEMD_SERVICE_UNIT


def is_systemd_service_process(env: dict[str, str] | None = None, pid: int | None = None) -> bool:
    current_env = os.environ if env is None else env
    current_pid = os.getpid() if pid is None else pid
    raw_exec_pid = (current_env.get("SYSTEMD_EXEC_PID") or "").strip()
    if not raw_exec_pid:
        return False
    try:
        return int(raw_exec_pid) == current_pid
    except ValueError:
        return False


class RuntimeRestartController:
    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self._restart_started = False

    def schedule_restart(self, operation: Awaitable[None]) -> None:
        if self._restart_started:
            return
        self._restart_started = True
        asyncio.create_task(operation)

    def mark_failed(self) -> None:
        self._restart_started = False
