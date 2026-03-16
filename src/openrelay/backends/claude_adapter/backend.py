from __future__ import annotations

from pathlib import Path
from typing import Any

from openrelay.agent_runtime import (
    AgentBackend,
    ApprovalDecision,
    ApprovalRequest,
    BackendCapabilities,
    ListSessionsRequest,
    RunningTurnHandle,
    RuntimeEventSink,
    SessionLocator,
    SessionSummary,
    SessionTranscript,
    StartSessionRequest,
    TurnInput,
)

from .client import ClaudeSessionClient
from .mapper import ClaudeResponseMapper
from .transport import ClaudeCliTransport


class ClaudeRuntimeBackend(AgentBackend):
    def __init__(self, claude_path: str, *, workspace_root: Path, default_model: str = "") -> None:
        self.claude_path = claude_path
        self.workspace_root = workspace_root
        self.default_model = default_model
        self._clients: dict[str, ClaudeSessionClient] = {}

    def name(self) -> str:
        return "claude"

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities()

    async def start_session(self, request: StartSessionRequest) -> SessionSummary:
        return await self._get_client(request.cwd).start_session(request)

    async def resume_session(self, locator: SessionLocator) -> SessionSummary:
        return await self._get_client("").resume_session(locator)

    async def list_sessions(self, request: ListSessionsRequest) -> tuple[list[SessionSummary], str]:
        return await self._get_client(request.cwd or "").list_sessions(request)

    async def read_session(self, locator: SessionLocator) -> SessionTranscript:
        return await self._get_client("").read_session(locator)

    async def start_turn(
        self,
        locator: SessionLocator,
        turn_input: TurnInput,
        sink: RuntimeEventSink,
    ) -> RunningTurnHandle:
        session_id = str(turn_input.metadata.get("relay_session_id") or locator.native_session_id or "")
        if not session_id:
            raise RuntimeError("relay_session_id is required in turn input metadata")
        return await self._get_client(turn_input.cwd).start_turn(locator, turn_input, sink, session_id)

    async def interrupt_turn(self, locator: SessionLocator, turn_id: str) -> None:
        await self._get_client("").interrupt_turn(locator, turn_id)

    async def resolve_approval(
        self,
        locator: SessionLocator,
        approval: ApprovalDecision,
        request: ApprovalRequest,
    ) -> None:
        await self._get_client("").resolve_approval(locator, approval, request)

    async def compact_session(self, locator: SessionLocator) -> dict[str, Any]:
        return await self._get_client("").compact_session(locator)

    async def shutdown(self) -> None:
        for client in list(self._clients.values()):
            await client.shutdown()
        self._clients.clear()

    def _get_client(self, cwd: str) -> ClaudeSessionClient:
        workspace_root = str(Path(cwd).expanduser().resolve()) if cwd else str(self.workspace_root.resolve())
        client = self._clients.get(workspace_root)
        if client is None:
            client = ClaudeSessionClient(
                transport=ClaudeCliTransport(self.claude_path, workspace_root=Path(workspace_root)),
                default_model=self.default_model,
                mapper=ClaudeResponseMapper(),
            )
            self._clients[workspace_root] = client
        return client
