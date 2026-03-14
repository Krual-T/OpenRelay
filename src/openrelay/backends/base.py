from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import os
from pathlib import Path

from openrelay.core import BackendReply, SessionRecord


ENV_WHITELIST = {
    "PATH", "HOME", "USER", "LOGNAME", "SHELL",
    "LANG", "LC_ALL", "LC_CTYPE",
    "TMPDIR", "TEMP", "TMP",
    "TERM", "COLORTERM",
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
    "SSH_AUTH_SOCK", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
}


@dataclass(slots=True)
class BackendContext:
    workspace_root: Path
    local_image_paths: tuple[str, ...] = ()
    on_partial_text: Callable[[str], Awaitable[None]] | None = None
    on_progress: Callable[[dict[str, object]], Awaitable[None]] | None = None
    on_server_request: Callable[[str, dict[str, object]], Awaitable[dict[str, object]]] | None = None
    cancel_event: asyncio.Event | None = None


class Backend(ABC):
    name: str

    @abstractmethod
    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        raise NotImplementedError



def build_subprocess_env(kind: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in ENV_WHITELIST or key.startswith("OPENRELAY_"):
            env[key] = value
    if kind == "codex":
        for key, value in os.environ.items():
            if key.startswith("OPENAI_") or key.startswith("CODEX_"):
                env[key] = value
    if kind == "claude":
        for key, value in os.environ.items():
            if key.startswith("ANTHROPIC_") or key.startswith("CLAUDE_"):
                env[key] = value
    return env



def safety_to_codex_approval(_safety_mode: str) -> str:
    return "never"



def safety_to_claude_flags(safety_mode: str) -> list[str]:
    if safety_mode == "danger-full-access":
        return ["--dangerously-skip-permissions"]
    if safety_mode == "workspace-write":
        return ["--permission-mode", "acceptEdits"]
    return ["--permission-mode", "plan"]
