from __future__ import annotations

import asyncio
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
DEFAULT_COMPACT_WAIT_SECONDS = 30.0
DEFAULT_COMPACT_POLL_SECONDS = 0.5


def _thread_status_type(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("type") or "").strip()
    if isinstance(value, str):
        return value.strip()
    return ""


def _count_context_compaction_items(thread: object) -> int:
    if not isinstance(thread, dict):
        return 0
    turns = thread.get("turns")
    if not isinstance(turns, list):
        return 0
    count = 0
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        items = turn.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and str(item.get("type") or "").strip() == "contextCompaction":
                count += 1
    return count


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
        compact_wait_seconds: float = DEFAULT_COMPACT_WAIT_SECONDS,
        compact_poll_seconds: float = DEFAULT_COMPACT_POLL_SECONDS,
    ) -> None:
        self.codex_path = codex_path
        self.workspace_root = workspace_root
        self.sqlite_home = sqlite_home
        self.model = model
        self.safety_mode = safety_mode
        self.request_timeout_seconds = request_timeout_seconds
        self.interrupt_grace_seconds = interrupt_grace_seconds
        self.resume_timeout_seconds = resume_timeout_seconds
        self.compact_wait_seconds = compact_wait_seconds
        self.compact_poll_seconds = compact_poll_seconds
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
        baseline_compactions = await self._read_context_compaction_count(thread_id)
        completion_future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()

        async def handle_notification(method: str, params: dict[str, Any]) -> None:
            if str(params.get("threadId") or "").strip() != thread_id:
                return
            if method == "thread/compacted" and not completion_future.done():
                completion_future.set_result(
                    {
                        "threadId": thread_id,
                        "status": "completed",
                        "completionSource": "notification",
                        "turnId": str(params.get("turnId") or "").strip(),
                    }
                )
                return
            if method != "thread/status/changed" or completion_future.done():
                return
            status = _thread_status_type(params.get("status"))
            if status == "systemError":
                completion_future.set_exception(RuntimeError(f"Codex compact failed for thread {thread_id}: thread entered systemError"))

        self.subscribe_notifications(handle_notification)
        try:
            started_result = await self._client.request("thread/compact/start", {"threadId": thread_id})
            started = started_result if isinstance(started_result, dict) else {}
            completion = await self._wait_for_compaction_completion(thread_id, baseline_compactions, completion_future)
        finally:
            self.unsubscribe_notifications(handle_notification)

        result = dict(started)
        result.setdefault("threadId", thread_id)
        result["status"] = "completed"
        if completion.get("completionSource"):
            result["completionSource"] = completion["completionSource"]
        if completion.get("turnId"):
            result["turnId"] = completion["turnId"]
        return result

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

    async def _read_context_compaction_count(self, thread_id: str) -> int:
        await self.ensure_started()
        assert self._client is not None
        result = await self._client.request("thread/read", {"threadId": thread_id, "includeTurns": True})
        thread = result.get("thread") if isinstance(result, dict) and isinstance(result.get("thread"), dict) else {}
        return _count_context_compaction_items(thread)

    async def _wait_for_compaction_completion(
        self,
        thread_id: str,
        baseline_compactions: int,
        completion_future: asyncio.Future[dict[str, Any]],
    ) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + max(self.compact_wait_seconds, self.compact_poll_seconds)
        while True:
            if completion_future.done():
                return await completion_future
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise RuntimeError(f"Codex compact timed out after {self.compact_wait_seconds:.0f}s for thread {thread_id}")
            sleep_task = asyncio.create_task(asyncio.sleep(min(self.compact_poll_seconds, remaining)))
            try:
                done, _ = await asyncio.wait({completion_future, sleep_task}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                sleep_task.cancel()
            if completion_future in done:
                return await completion_future
            await self.ensure_started()
            assert self._client is not None
            result = await self._client.request("thread/read", {"threadId": thread_id, "includeTurns": True})
            thread = result.get("thread") if isinstance(result, dict) and isinstance(result.get("thread"), dict) else {}
            status = _thread_status_type(thread.get("status"))
            if status == "systemError":
                raise RuntimeError(f"Codex compact failed for thread {thread_id}: thread entered systemError")
            if _count_context_compaction_items(thread) > baseline_compactions:
                return {
                    "threadId": thread_id,
                    "status": "completed",
                    "completionSource": "thread_read",
                }
