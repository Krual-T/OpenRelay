from __future__ import annotations

import asyncio
from asyncio.subprocess import PIPE
from dataclasses import dataclass
from pathlib import Path

from openrelay.backends.base import build_subprocess_env, safety_to_claude_flags


@dataclass(slots=True, frozen=True)
class ClaudeCliResult:
    stdout: str
    stderr: str


class ClaudeCliTransport:
    def __init__(self, claude_path: str, *, workspace_root: Path) -> None:
        self.claude_path = claude_path
        self.workspace_root = workspace_root

    async def run(
        self,
        *,
        prompt: str,
        cwd: str,
        model: str | None,
        safety_mode: str,
        session_id: str = "",
        cancel_event: asyncio.Event | None = None,
    ) -> ClaudeCliResult:
        args = [
            self.claude_path,
            "--print",
            "--output-format",
            "json",
            "--cwd",
            cwd or str(self.workspace_root),
        ]
        if model:
            args.extend(["--model", model])
        if session_id:
            args.extend(["--resume", session_id])
        args.extend(safety_to_claude_flags(safety_mode))
        args.append(prompt)

        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
            env=build_subprocess_env("claude"),
        )

        async def cancel_watcher() -> None:
            if cancel_event is None:
                return
            await cancel_event.wait()
            if process.returncode is None:
                process.terminate()

        watcher = asyncio.create_task(cancel_watcher())
        try:
            stdout, stderr = await process.communicate()
        finally:
            watcher.cancel()

        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if process.returncode not in {0, None}:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Claude runtime turn interrupted")
            raise RuntimeError(stderr_text or f"Claude CLI exited with code {process.returncode}")
        return ClaudeCliResult(
            stdout=stdout.decode("utf-8", errors="replace").strip(),
            stderr=stderr_text,
        )
