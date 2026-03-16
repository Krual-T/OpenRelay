from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
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
from openrelay.agent_runtime.events import RuntimeEvent, SessionStartedEvent
from openrelay.agent_runtime.models import TranscriptMessage
from openrelay.backends.codex import (
    DEFAULT_INTERRUPT_GRACE_SECONDS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_RESUME_TIMEOUT_SECONDS,
    STOP_INTERRUPT_REASON,
    CodexAppServerClient,
)

from .mapper import CodexProtocolMapper


def _thread_summary_to_session(summary: Any) -> SessionSummary:
    return SessionSummary(
        backend="codex",
        native_session_id=summary.thread_id,
        title=summary.name or summary.preview or summary.thread_id,
        preview=summary.preview,
        cwd=summary.cwd,
        updated_at=summary.updated_at,
        status=summary.status,
    )


def _thread_details_to_transcript(details: Any) -> SessionTranscript:
    messages = tuple(
        TranscriptMessage(role=message.role, text=message.text)
        for message in details.messages
    )
    return SessionTranscript(
        summary=SessionSummary(
            backend="codex",
            native_session_id=details.thread_id,
            title=details.name or details.preview or details.thread_id,
            preview=details.preview,
            cwd=details.cwd,
            updated_at=details.updated_at,
            status=details.status,
        ),
        messages=messages,
    )


@dataclass(slots=True)
class _PendingApproval:
    request: ApprovalRequest
    future: asyncio.Future[dict[str, Any]]


@dataclass(slots=True)
class _CodexRuntimeTurnHandle(RunningTurnHandle):
    session_id: str
    turn_id: str
    backend: str
    future: asyncio.Future[None]

    async def wait(self) -> None:
        await self.future


class _RuntimeCodexTurn:
    def __init__(
        self,
        *,
        client: CodexAppServerClient,
        sink: RuntimeEventSink,
        mapper: CodexProtocolMapper,
        backend: "CodexRuntimeBackend",
        session_id: str,
        thread_id: str,
    ) -> None:
        self.client = client
        self.sink = sink
        self.mapper = mapper
        self.backend = backend
        self.session_id = session_id
        self.thread_id = thread_id
        self.turn_id = mapper.turn_id
        self.done = False
        self.future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.interrupted = False
        self.interrupt_message = STOP_INTERRUPT_REASON
        self.interrupt_sent = False

    async def set_turn_id(self, turn_id: str) -> None:
        self.turn_id = turn_id or self.turn_id
        self.mapper.turn_id = self.turn_id

    async def interrupt(self, reason: str = STOP_INTERRUPT_REASON) -> None:
        self.interrupted = True
        self.interrupt_message = reason
        if not self.turn_id or self.interrupt_sent:
            return
        self.interrupt_sent = True
        try:
            await self.client.request("turn/interrupt", {"threadId": self.thread_id, "turnId": self.turn_id})
        except Exception:
            return

    async def handle_notification(self, _client: CodexAppServerClient, method: str, params: dict[str, Any]) -> None:
        if self.done:
            return
        events = self.mapper.map_notification(method, params)
        self.turn_id = self.mapper.turn_id or self.turn_id
        terminal_error: BaseException | None = None
        try:
            for event in events:
                await self.sink.publish(event)
                if event.event_type == "turn.completed":
                    self.done = True
                    if not self.future.done():
                        self.future.set_result(None)
                elif event.event_type == "turn.interrupted":
                    self.done = True
                    terminal_error = InterruptedError(getattr(event, "message", self.interrupt_message))
                elif event.event_type == "turn.failed":
                    self.done = True
                    terminal_error = RuntimeError(getattr(event, "message", "turn failed"))
        except BaseException as exc:
            self.done = True
            terminal_error = exc
        if terminal_error is not None and not self.future.done():
            self.future.set_exception(terminal_error)

    async def handle_server_request(
        self,
        client: CodexAppServerClient,
        request_id: int | str,
        method: str,
        params: dict[str, Any],
    ) -> bool:
        if self.done:
            return False
        requested = self.mapper.map_server_request(request_id, method, params)
        if requested is None:
            return False
        pending = _PendingApproval(
            request=requested.request,
            future=asyncio.get_running_loop().create_future(),
        )
        self.backend.remember_pending_approval(pending)
        await self.sink.publish(requested)
        try:
            result = await pending.future
        finally:
            self.backend.forget_pending_approval(requested.request.approval_id)
        await client._send_server_result(request_id, result)
        return True


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
        self._clients: dict[tuple[str, str, str], CodexAppServerClient] = {}
        self.pending_approvals: dict[str, _PendingApproval] = {}
        self.active_turns: dict[tuple[str, str], _RuntimeCodexTurn] = {}

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
        result = await client.request("thread/start", self._build_thread_params(request.cwd, request.model, request.safety_mode))
        thread = result.get("thread") if isinstance(result, dict) and isinstance(result.get("thread"), dict) else {}
        thread_id = str(thread.get("id") or "")
        return SessionSummary(
            backend="codex",
            native_session_id=thread_id,
            title=str(thread.get("name") or thread.get("preview") or thread_id),
            preview=str(thread.get("preview") or ""),
            cwd=request.cwd,
            updated_at=str(thread.get("updatedAt") or ""),
            status=str(thread.get("status") or ""),
        )

    async def resume_session(self, locator: SessionLocator) -> SessionSummary:
        return (await self.read_session(locator)).summary

    async def list_sessions(self, request: ListSessionsRequest) -> tuple[list[SessionSummary], str]:
        workspace_root = self._resolve_workspace_root(request.cwd or "")
        client = self._get_client(
            workspace_root=workspace_root,
            session_token=f"list:{request.cwd or workspace_root}",
            model=self.default_model,
            safety_mode="workspace-write",
        )
        summaries, cursor = await client.list_threads(limit=request.limit)
        return ([_thread_summary_to_session(summary) for summary in summaries], cursor)

    async def read_session(self, locator: SessionLocator) -> SessionTranscript:
        client = self._get_client(
            workspace_root=self.workspace_root,
            session_token=f"thread:{locator.native_session_id}",
            model=self.default_model,
            safety_mode="workspace-write",
        )
        details = await client.read_thread(locator.native_session_id, include_turns=True)
        return _thread_details_to_transcript(details)

    async def start_turn(
        self,
        locator: SessionLocator,
        turn_input: TurnInput,
        sink: RuntimeEventSink,
    ) -> RunningTurnHandle:
        session_id = str(turn_input.metadata.get("relay_session_id") or locator.native_session_id or "")
        if not session_id:
            raise RuntimeError("relay_session_id is required in turn input metadata")
        workspace_root = self._resolve_workspace_root(turn_input.cwd)
        client = self._get_client(
            workspace_root=workspace_root,
            session_token=session_id,
            model=turn_input.model or self.default_model,
            safety_mode=turn_input.safety_mode,
        )
        thread_id = await self._ensure_thread(client, locator, turn_input, sink, session_id)
        mapper = CodexProtocolMapper(session_id=session_id, native_session_id=thread_id)
        turn = _RuntimeCodexTurn(
            client=client,
            sink=sink,
            mapper=mapper,
            backend=self,
            session_id=session_id,
            thread_id=thread_id,
        )
        client.active_turns.add(turn)  # type: ignore[arg-type]
        handle = _CodexRuntimeTurnHandle(
            session_id=session_id,
            turn_id="",
            backend="codex",
            future=turn.future,
        )

        async def drive() -> None:
            try:
                result = await client.request(
                    "turn/start",
                    self._build_turn_start_params(thread_id, turn_input),
                )
                turn_id = str(result.get("turn", {}).get("id") or "")
                await turn.set_turn_id(turn_id)
                handle.turn_id = turn.turn_id
            except BaseException as exc:
                turn.done = True
                if not turn.future.done():
                    turn.future.set_exception(exc)
            finally:
                if turn.done:
                    client.active_turns.discard(turn)  # type: ignore[arg-type]

        turn.future.add_done_callback(lambda _future: client.active_turns.discard(turn))  # type: ignore[arg-type]
        asyncio.create_task(drive())
        return handle

    async def interrupt_turn(self, locator: SessionLocator, turn_id: str) -> None:
        turn = self.active_turns.get((locator.native_session_id, turn_id))
        if turn is not None:
            await turn.interrupt()
            return
        client = self._get_client(
            workspace_root=self.workspace_root,
            session_token=f"thread:{locator.native_session_id}",
            model=self.default_model,
            safety_mode="workspace-write",
        )
        await client.request("turn/interrupt", {"threadId": locator.native_session_id, "turnId": turn_id})

    async def resolve_approval(
        self,
        locator: SessionLocator,
        approval: ApprovalDecision,
        request: ApprovalRequest,
    ) -> None:
        _ = locator
        pending = self.pending_approvals.get(request.approval_id)
        if pending is None:
            raise KeyError(f"Unknown approval request: {request.approval_id}")
        response = CodexProtocolMapper(
            session_id=request.session_id,
            native_session_id=locator.native_session_id,
            turn_id=request.turn_id,
        ).build_approval_response(request, approval)
        if not pending.future.done():
            pending.future.set_result(response)

    async def compact_session(self, locator: SessionLocator) -> dict[str, Any]:
        client = self._get_client(
            workspace_root=self.workspace_root,
            session_token=f"thread:{locator.native_session_id}",
            model=self.default_model,
            safety_mode="workspace-write",
        )
        return await client.compact_thread(locator.native_session_id)

    async def shutdown(self) -> None:
        for client in list(self._clients.values()):
            await client.shutdown()
        self._clients.clear()

    def remember_pending_approval(self, pending: _PendingApproval) -> None:
        self.pending_approvals[pending.request.approval_id] = pending

    def forget_pending_approval(self, approval_id: str) -> None:
        self.pending_approvals.pop(approval_id, None)

    def _get_client(
        self,
        *,
        workspace_root: Path,
        session_token: str,
        model: str,
        safety_mode: str,
    ) -> CodexAppServerClient:
        key = (self.codex_path, str(workspace_root), session_token)
        client = self._clients.get(key)
        if client is None:
            client = CodexAppServerClient(
                codex_path=self.codex_path,
                workspace_root=workspace_root,
                sqlite_home=self.sqlite_home,
                model=model,
                safety_mode=safety_mode,
                request_timeout_seconds=self.request_timeout_seconds,
                interrupt_grace_seconds=self.interrupt_grace_seconds,
                resume_timeout_seconds=self.resume_timeout_seconds,
            )
            self._clients[key] = client
        return client

    def _resolve_workspace_root(self, cwd: str) -> Path:
        return Path(cwd).expanduser().resolve() if cwd else self.workspace_root.resolve()

    def _build_thread_params(self, cwd: str, model: str | None, safety_mode: str) -> dict[str, Any]:
        params = {
            "cwd": cwd,
            "model": model or self.default_model or None,
            "sandbox": safety_mode,
            "approvalPolicy": "never",
        }
        return {key: value for key, value in params.items() if value not in {None, ""}}

    def _build_turn_start_params(self, thread_id: str, turn_input: TurnInput) -> dict[str, Any]:
        return {
            "threadId": thread_id,
            "cwd": turn_input.cwd,
            "approvalPolicy": "never",
            **({"model": turn_input.model} if turn_input.model else {}),
            "input": self._build_turn_input(turn_input),
        }

    def _build_turn_input(self, turn_input: TurnInput) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if turn_input.text.strip():
            items.append({"type": "text", "text": turn_input.text})
        for path in turn_input.local_image_paths:
            items.append({"type": "localImage", "path": path})
        return items

    async def _ensure_thread(
        self,
        client: CodexAppServerClient,
        locator: SessionLocator,
        turn_input: TurnInput,
        sink: RuntimeEventSink,
        session_id: str,
    ) -> str:
        if locator.native_session_id:
            await client.request(
                "thread/resume",
                {**self._build_thread_params(turn_input.cwd, turn_input.model, turn_input.safety_mode), "threadId": locator.native_session_id},
            )
            return locator.native_session_id
        result = await client.request(
            "thread/start",
            self._build_thread_params(turn_input.cwd, turn_input.model, turn_input.safety_mode),
        )
        thread = result.get("thread") if isinstance(result, dict) and isinstance(result.get("thread"), dict) else {}
        thread_id = str(thread.get("id") or "")
        if not thread_id:
            raise RuntimeError("Codex app-server returned no thread id")
        await sink.publish(
            SessionStartedEvent(
                backend="codex",
                session_id=session_id,
                turn_id="",
                event_type="session.started",
                native_session_id=thread_id,
                title=str(thread.get("name") or thread.get("preview") or ""),
                provider_payload={"native_session_id": thread_id},
            )
        )
        return thread_id
