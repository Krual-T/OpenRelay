"""
CodexV2Client — 单一 Codex CLI 子进程管理器。

管理一个 codex app-server 子进程的长连接：
- 启动子进程（stdin/stdout pipe）
- 后台读 stdout，解析 JSON-RPC
- 发送 request 并等待 response
- 发送 notification
- notification 回调（喂给 TurnV2Renderer）
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from asyncio.subprocess import PIPE, Process
from collections.abc import Callable
from pathlib import Path
from typing import Any

from openrelay.backends.base import build_subprocess_env

from .jsonrpc import (
    JSONRPCError,
    JSONRPCNotification,
    JSONRPCResponse,
    parse_jsonrpc_message,
    serialize_jsonrpc_message,
    to_jsonrpc_payload,
)
from .notifications import ServerNotification, parse_server_notification
from .requests import ServerRequest, parse_server_request

LOGGER = logging.getLogger("openrelay.backends.codex_adapter_v2.client")

STDOUT_READ_CHUNK_SIZE = 8192
DEFAULT_REQUEST_TIMEOUT = 120.0


class CodexV2ClientError(Exception):
    """CodexV2Client 操作失败。"""


class ConnectionClosedError(CodexV2ClientError):
    """子进程已退出。"""


NotificationHandler = Callable[[ServerNotification], None]
ServerRequestHandler = Callable[[ServerRequest], None]


class CodexV2Client:
    """管理一个 codex app-server 子进程的 JSON-RPC 连接。"""

    def __init__(
        self,
        codex_path: str,
        workspace_root: Path,
        *,
        model: str = "",
        safety_mode: str = "workspace-write",
        sqlite_home: Path | None = None,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        env_extra: dict[str, str] | None = None,
    ) -> None:
        self.codex_path = codex_path
        self.workspace_root = workspace_root
        self.model = model
        self.safety_mode = safety_mode
        self.sqlite_home = sqlite_home or Path.home() / ".openrelay" / "data"
        self.request_timeout = request_timeout
        self.env_extra = env_extra or {}

        self.process: Process | None = None
        self._request_id: int = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._notification_handler: NotificationHandler | None = None
        self._server_request_handler: ServerRequestHandler | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._wait_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self.last_active_at: float = 0.0
        self.stderr_text: str = ""

    # ---- lifecycle ----

    async def start(self) -> None:
        """启动 codex CLI 子进程并完成初始化握手。"""
        async with self._lock:
            if self.process is not None:
                return

            env = self._build_env()
            self.sqlite_home.mkdir(parents=True, exist_ok=True)

            self.process = await asyncio.create_subprocess_exec(
                self.codex_path,
                "app-server",
                stdin=PIPE,
                stdout=PIPE,
                stderr=PIPE,
                cwd=str(self.workspace_root),
                env=env,
            )
            self._stdout_task = asyncio.create_task(self._read_stdout())
            self._stderr_task = asyncio.create_task(self._read_stderr())
            self._wait_task = asyncio.create_task(self._watch_process())
            self.touch()

            # LSP-style initialize 握手
            await self.request("initialize", self._build_init_params())
            LOGGER.info("codex app-server initialized path=%s", self.codex_path)

    async def shutdown(self) -> None:
        """关闭连接，终止子进程。"""
        process = self.process
        self.process = None

        if self._stdout_task is not None:
            self._stdout_task.cancel()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
        if self._wait_task is not None:
            self._wait_task.cancel()

        # reject all pending futures
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionClosedError("connection closed"))
        self._pending.clear()

        if process is not None:
            await self._terminate_process(process)

    # ---- request / notify ----

    async def request(self, method: str, params: Any = None) -> dict[str, Any]:
        """发送 JSON-RPC request，等待并返回 result。"""
        await self._ensure_ready()
        request_id = self._next_id()
        payload = to_jsonrpc_payload(self._make_request(request_id, method, params))
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        await self._send(payload)
        try:
            return await asyncio.wait_for(future, timeout=self.request_timeout)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            raise CodexV2ClientError(f"request timeout: {method}") from None

    async def notify(self, method: str, params: Any = None) -> None:
        """发送 JSON-RPC notification（无响应）。"""
        await self._ensure_ready()
        payload: dict[str, Any] = {"method": method}
        if params is not None:
            payload["params"] = params
        await self._send(payload)

    def on_notification(self, handler: NotificationHandler) -> None:
        """注册 ServerNotification 回调。"""
        self._notification_handler = handler

    def on_server_request(self, handler: ServerRequestHandler) -> None:
        """注册 ServerRequest 回调。"""
        self._server_request_handler = handler

    def touch(self) -> None:
        """更新最后活动时间。"""
        self.last_active_at = time.monotonic()

    # ---- internal ----

    async def _ensure_ready(self) -> None:
        if self.process is None:
            await self.start()

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    @staticmethod
    def _make_request(request_id: int, method: str, params: Any) -> Any:
        from .jsonrpc import JSONRPCRequest
        return JSONRPCRequest(id=request_id, method=method, params=params)

    async def _send(self, payload: dict[str, Any]) -> None:
        assert self.process is not None and self.process.stdin is not None
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self.process.stdin.write(line.encode("utf-8") + b"\n")
        await self.process.stdin.drain()

    def _build_env(self) -> dict[str, str]:
        env = build_subprocess_env("codex")
        env["CODEX_SQLITE_HOME"] = str(self.sqlite_home)
        env.update(self.env_extra)
        return env

    def _build_init_params(self) -> dict[str, Any]:
        return {
            "clientInfo": {"name": "openrelay", "version": "0.1.0"},
            "cwd": str(self.workspace_root),
            **({"model": self.model} if self.model else {}),
            "sandbox": self.safety_mode,
        }

    # ---- stdout / stderr ----

    async def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        pending = bytearray()
        try:
            while True:
                chunk = await self.process.stdout.read(STDOUT_READ_CHUNK_SIZE)
                if not chunk:
                    if pending:
                        await self._handle_line(bytes(pending))
                    return
                pending.extend(chunk)
                while True:
                    idx = pending.find(b"\n")
                    if idx < 0:
                        break
                    line = bytes(pending[:idx])
                    del pending[: idx + 1]
                    await self._handle_line(line)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("stdout reader failed")

    async def _handle_line(self, line: bytes) -> None:
        raw = line.decode("utf-8", errors="replace").strip()
        if not raw:
            return
        self.touch()
        try:
            msg = parse_jsonrpc_message(raw)
        except Exception:
            LOGGER.debug("unparseable JSON-RPC: %s", raw[:200])
            return

        if isinstance(msg, (JSONRPCResponse, JSONRPCError)):
            rid = msg.id
            future = self._pending.pop(rid, None)
            if future is None:
                return
            if isinstance(msg, JSONRPCError):
                future.set_exception(
                    CodexV2ClientError(f"JSON-RPC error {msg.error.code}: {msg.error.message}")
                )
            else:
                future.set_result(msg.result)

        elif isinstance(msg, JSONRPCNotification):
            notification = parse_server_notification(msg)
            if notification is not None and self._notification_handler is not None:
                try:
                    self._notification_handler(notification)
                except Exception:
                    LOGGER.exception("notification handler failed variant=%s", notification.variant)

        elif hasattr(msg, "method") and hasattr(msg, "id"):
            # JSONRPCRequest from server → needs response
            try:
                request = parse_server_request(msg)  # type: ignore[arg-type]
            except Exception:
                LOGGER.debug("unhandled server request: %s", raw[:200])
                return
            if self._server_request_handler is not None:
                try:
                    self._server_request_handler(request)
                except Exception:
                    LOGGER.exception("server request handler failed variant=%s", request.variant)

    async def _read_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        try:
            while True:
                line = await self.process.stderr.readline()
                if not line:
                    return
                self.stderr_text += line.decode("utf-8", errors="replace")
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("stderr reader failed")

    async def _watch_process(self) -> None:
        assert self.process is not None
        code = await self.process.wait()
        LOGGER.warning("codex app-server exited code=%s stderr=%s", code, self.stderr_text[:500])

    @staticmethod
    async def _terminate_process(process: Process) -> None:
        try:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        except ProcessLookupError:
            pass
