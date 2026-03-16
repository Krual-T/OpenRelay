from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

from openrelay.backends.codex_adapter.app_server import (
    DEFAULT_INTERRUPT_GRACE_SECONDS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_RESUME_TIMEOUT_SECONDS,
    CodexAppServerClient,
)

NotificationSubscriber = Callable[[str, dict[str, Any]], Awaitable[None]]
ServerRequestSubscriber = Callable[[int | str, str, dict[str, Any]], Awaitable[bool]]


class _TransportBridge:
    def __init__(self, transport: "CodexRpcTransport") -> None:
        self.transport = transport

    async def handle_notification(
        self,
        _client: CodexAppServerClient,
        method: str,
        params: dict[str, Any],
    ) -> None:
        await self.transport._dispatch_notification(method, params)

    async def handle_server_request(
        self,
        _client: CodexAppServerClient,
        request_id: int | str,
        method: str,
        params: dict[str, Any],
    ) -> bool:
        return await self.transport._dispatch_server_request(request_id, method, params)


class CodexRpcTransport:
    def __init__(
        self,
        *,
        codex_path: str,
        workspace_root: Path,
        sqlite_home: Path,
        model: str,
        safety_mode: str,
        request_timeout_seconds: float | None = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        interrupt_grace_seconds: float = DEFAULT_INTERRUPT_GRACE_SECONDS,
        resume_timeout_seconds: float = DEFAULT_RESUME_TIMEOUT_SECONDS,
    ) -> None:
        self.codex_path = codex_path
        self.workspace_root = workspace_root
        self.sqlite_home = sqlite_home
        self.model = model
        self.safety_mode = safety_mode
        self.request_timeout_seconds = request_timeout_seconds
        self.interrupt_grace_seconds = interrupt_grace_seconds
        self.resume_timeout_seconds = resume_timeout_seconds
        self.pending_requests: dict[int | str, object] = {}
        self.notification_subscribers: list[NotificationSubscriber] = []
        self.server_request_subscribers: list[ServerRequestSubscriber] = []
        self._client: CodexAppServerClient | None = None
        self._bridge = _TransportBridge(self)

    async def start(self) -> None:
        await self.ensure_started()

    async def stop(self) -> None:
        client = self._client
        self._client = None
        if client is None:
            return
        client.active_turns.discard(self._bridge)  # type: ignore[arg-type]
        await client.shutdown()

    async def ensure_started(self) -> None:
        if self._client is not None:
            return
        client = CodexAppServerClient(
            codex_path=self.codex_path,
            workspace_root=self.workspace_root,
            sqlite_home=self.sqlite_home,
            model=self.model,
            safety_mode=self.safety_mode,
            request_timeout_seconds=self.request_timeout_seconds,
            interrupt_grace_seconds=self.interrupt_grace_seconds,
            resume_timeout_seconds=self.resume_timeout_seconds,
        )
        client.active_turns.add(self._bridge)  # type: ignore[arg-type]
        self._client = client

    async def request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        cancel_event: object | None = None,
    ) -> Any:
        await self.ensure_started()
        assert self._client is not None
        return await self._client.request(method, params, cancel_event=cancel_event)

    async def list_threads(self, *, limit: int = 20) -> tuple[list[object], str]:
        await self.ensure_started()
        assert self._client is not None
        return await self._client.list_threads(limit=limit)

    async def read_thread(self, thread_id: str, *, include_turns: bool = True) -> object:
        await self.ensure_started()
        assert self._client is not None
        return await self._client.read_thread(thread_id, include_turns=include_turns)

    async def compact_thread(self, thread_id: str) -> dict[str, Any]:
        await self.ensure_started()
        assert self._client is not None
        return await self._client.compact_thread(thread_id)

    async def send_result(self, request_id: int | str, result: dict[str, Any]) -> None:
        await self.ensure_started()
        assert self._client is not None
        await self._client._send_server_result(request_id, result)

    async def send_error(
        self,
        request_id: int | str,
        code: int,
        message: str,
        data: Any = None,
    ) -> None:
        await self.ensure_started()
        assert self._client is not None
        await self._client._send_server_error(request_id, code, message, data)

    def subscribe_notifications(self, callback: NotificationSubscriber) -> None:
        self.notification_subscribers.append(callback)

    def unsubscribe_notifications(self, callback: NotificationSubscriber) -> None:
        if callback in self.notification_subscribers:
            self.notification_subscribers.remove(callback)

    def subscribe_server_requests(self, callback: ServerRequestSubscriber) -> None:
        self.server_request_subscribers.append(callback)

    def unsubscribe_server_requests(self, callback: ServerRequestSubscriber) -> None:
        if callback in self.server_request_subscribers:
            self.server_request_subscribers.remove(callback)

    async def _dispatch_notification(self, method: str, params: dict[str, Any]) -> None:
        for callback in list(self.notification_subscribers):
            await callback(method, params)

    async def _dispatch_server_request(
        self,
        request_id: int | str,
        method: str,
        params: dict[str, Any],
    ) -> bool:
        for callback in list(self.server_request_subscribers):
            if await callback(request_id, method, params):
                return True
        return False
