from __future__ import annotations

from pathlib import Path

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
from openrelay.backends.codex import (
    DEFAULT_INTERRUPT_GRACE_SECONDS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_RESUME_TIMEOUT_SECONDS,
)

from .client import CodexSessionClient
from .mapper import CodexProtocolMapper
from .transport import CodexRpcTransport


class CodexRuntimeBackend(AgentBackend):
    def __init__(
        self,
        codex_path: str,
        default_model: str,
        *,
        workspace_root: Path,
        sqlite_home: Path,
        request_timeout_seconds: float | None = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        interrupt_grace_seconds: float = DEFAULT_INTERRUPT_GRACE_SECONDS,
        resume_timeout_seconds: float = DEFAULT_RESUME_TIMEOUT_SECONDS,
    ) -> None:
        self.codex_path = codex_path
        self.default_model = default_model
        self.workspace_root = workspace_root
        self.sqlite_home = sqlite_home
        self.request_timeout_seconds = request_timeout_seconds
        self.interrupt_grace_seconds = interrupt_grace_seconds
        self.resume_timeout_seconds = resume_timeout_seconds
        self._clients: dict[tuple[str, str, str], CodexSessionClient] = {}

    def name(self) -> str:
        return "codex"

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            supports_session_list=True,
            supports_session_read=True,
            supports_compact=True,
            supports_plan_updates=True,
            supports_reasoning_stream=True,
            supports_file_change_approval=True,
            supports_command_approval=True,
        )

    async def start_session(self, request: StartSessionRequest) -> SessionSummary:
        client = self._get_client(
            workspace_root=self._resolve_workspace_root(request.cwd),
            session_token=f"bootstrap:{request.cwd}",
            model=request.model or self.default_model,
            safety_mode=request.safety_mode,
        )
        return await client.start_session(request)

    async def resume_session(self, locator: SessionLocator) -> SessionSummary:
        client = self._get_client(
            workspace_root=self.workspace_root,
            session_token=f"thread:{locator.native_session_id}",
            model=self.default_model,
            safety_mode="workspace-write",
        )
        return await client.resume_session(locator)

    async def list_sessions(self, request: ListSessionsRequest) -> tuple[list[SessionSummary], str]:
        workspace_root = self._resolve_workspace_root(request.cwd or "")
        client = self._get_client(
            workspace_root=workspace_root,
            session_token=f"list:{request.cwd or workspace_root}",
            model=self.default_model,
            safety_mode="workspace-write",
        )
        return await client.list_sessions(request)

    async def read_session(self, locator: SessionLocator) -> SessionTranscript:
        client = self._get_client(
            workspace_root=self.workspace_root,
            session_token=f"thread:{locator.native_session_id}",
            model=self.default_model,
            safety_mode="workspace-write",
        )
        return await client.read_session(locator)

    async def start_turn(
        self,
        locator: SessionLocator,
        turn_input: TurnInput,
        sink: RuntimeEventSink,
    ) -> RunningTurnHandle:
        session_id = str(turn_input.metadata.get("relay_session_id") or locator.native_session_id or "")
        if not session_id:
            raise RuntimeError("relay_session_id is required in turn input metadata")
        client = self._get_client(
            workspace_root=self._resolve_workspace_root(turn_input.cwd),
            session_token=session_id,
            model=turn_input.model or self.default_model,
            safety_mode=turn_input.safety_mode,
        )
        return await client.start_turn(locator, turn_input, sink, session_id)

    async def interrupt_turn(self, locator: SessionLocator, turn_id: str) -> None:
        client = self._get_client(
            workspace_root=self.workspace_root,
            session_token=f"thread:{locator.native_session_id}",
            model=self.default_model,
            safety_mode="workspace-write",
        )
        await client.interrupt_turn(locator, turn_id)

    async def resolve_approval(
        self,
        locator: SessionLocator,
        approval: ApprovalDecision,
        request: ApprovalRequest,
    ) -> None:
        client = self._get_client(
            workspace_root=self.workspace_root,
            session_token=request.session_id,
            model=self.default_model,
            safety_mode="workspace-write",
        )
        await client.resolve_approval(locator, approval, request)

    async def compact_session(self, locator: SessionLocator) -> dict[str, Any]:
        client = self._get_client(
            workspace_root=self.workspace_root,
            session_token=f"thread:{locator.native_session_id}",
            model=self.default_model,
            safety_mode="workspace-write",
        )
        return await client.compact_session(locator)

    async def shutdown(self) -> None:
        for client in list(self._clients.values()):
            await client.shutdown()
        self._clients.clear()

    def _get_client(
        self,
        *,
        workspace_root: Path,
        session_token: str,
        model: str,
        safety_mode: str,
    ) -> CodexSessionClient:
        key = (self.codex_path, str(workspace_root), session_token)
        client = self._clients.get(key)
        if client is None:
            transport = CodexRpcTransport(
                codex_path=self.codex_path,
                workspace_root=workspace_root,
                sqlite_home=self.sqlite_home,
                model=model,
                safety_mode=safety_mode,
                request_timeout_seconds=self.request_timeout_seconds,
                interrupt_grace_seconds=self.interrupt_grace_seconds,
                resume_timeout_seconds=self.resume_timeout_seconds,
            )
            client = CodexSessionClient(
                transport=transport,
                default_model=self.default_model,
                mapper_factory=CodexProtocolMapper,
            )
            self._clients[key] = client
        return client

    def _resolve_workspace_root(self, cwd: str) -> Path:
        return Path(cwd).expanduser().resolve() if cwd else self.workspace_root.resolve()
