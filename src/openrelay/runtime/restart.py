from __future__ import annotations

import asyncio
import logging
import os
import sys

from openrelay.backends.codex import CodexAppServerClient

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

    def schedule_restart(self) -> None:
        if self._restart_started:
            return
        self._restart_started = True
        asyncio.create_task(self._restart_process())

    def mark_failed(self) -> None:
        self._restart_started = False

    async def _restart_process(self) -> None:
        await asyncio.sleep(0.4)
        if is_systemd_service_process():
            unit_name = get_systemd_service_unit()
            try:
                await self._restart_systemd_service(unit_name)
                return
            except Exception:
                self.mark_failed()
                self.logger.exception("failed to restart %s via systemd", unit_name)
                raise
        try:
            await CodexAppServerClient.shutdown_all()
        except Exception:
            self.logger.exception("failed shutting down backends before restart")
        try:
            os.execvpe(sys.executable, [sys.executable, "-m", "openrelay"], os.environ)
        except Exception:
            self.mark_failed()
            self.logger.exception("failed to restart openrelay process")
            raise

    async def _restart_systemd_service(self, unit_name: str) -> None:
        process = await asyncio.create_subprocess_exec(
            "systemctl",
            "--user",
            "--no-block",
            "restart",
            unit_name,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=dict(os.environ),
        )
        stderr = b""
        if process.stderr is not None:
            stderr = await process.stderr.read()
        exit_code = await process.wait()
        if exit_code == 0:
            return
        detail = stderr.decode("utf-8", errors="replace").strip()
        message = detail or f"systemctl --user restart exited with code {exit_code}"
        raise RuntimeError(message)
