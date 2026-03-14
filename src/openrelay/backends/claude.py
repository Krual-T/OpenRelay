from __future__ import annotations

import asyncio
import json
from asyncio.subprocess import PIPE
from typing import Any

from openrelay.backends.base import Backend, BackendContext, build_subprocess_env, safety_to_claude_flags
from openrelay.core import BackendReply, SessionRecord


class ClaudeCodeBackend(Backend):
    name = "claude"

    def __init__(self, claude_path: str):
        self.claude_path = claude_path

    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        args = [
            self.claude_path,
            "--print",
            "--output-format",
            "json",
            "--cwd",
            session.cwd,
        ]
        if session.model_override:
            args.extend(["--model", session.model_override])
        if session.native_session_id:
            args.extend(["--resume", session.native_session_id])
        args.extend(safety_to_claude_flags(session.safety_mode))
        args.append(prompt)

        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
            env=build_subprocess_env("claude"),
        )

        async def cancel_watcher() -> None:
            if context.cancel_event is None:
                return
            await context.cancel_event.wait()
            process.terminate()

        watcher = asyncio.create_task(cancel_watcher())
        try:
            stdout, stderr = await process.communicate()
        finally:
            watcher.cancel()

        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if process.returncode not in {0, None}:
            if context.cancel_event is not None and context.cancel_event.is_set():
                raise RuntimeError("Claude Code run interrupted")
            raise RuntimeError(stderr_text or f"Claude Code exited with code {process.returncode}")

        payload_text = stdout.decode("utf-8", errors="replace").strip()
        if not payload_text:
            raise RuntimeError(stderr_text or "Claude Code returned no output")
        reply = self._parse_output(payload_text)
        if context.on_partial_text is not None and reply.text:
            await context.on_partial_text(reply.text)
        return reply

    def _parse_output(self, payload_text: str) -> BackendReply:
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            return BackendReply(text=payload_text)

        if isinstance(payload, dict):
            text = self._extract_text(payload)
            session_id = str(payload.get("session_id") or payload.get("sessionId") or "")
            return BackendReply(text=text or payload_text, native_session_id=session_id, metadata=payload)
        return BackendReply(text=payload_text)

    def _extract_text(self, payload: dict[str, Any]) -> str:
        if isinstance(payload.get("result"), str) and payload["result"].strip():
            return payload["result"].strip()
        if isinstance(payload.get("text"), str) and payload["text"].strip():
            return payload["text"].strip()
        message = payload.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                if parts:
                    return "\n".join(parts).strip()
        return ""
