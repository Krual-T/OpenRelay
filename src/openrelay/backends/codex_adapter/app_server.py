from __future__ import annotations

import asyncio
import json
import logging
from asyncio.subprocess import PIPE, Process
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

from openrelay.backends.base import build_subprocess_env

DEFAULT_REQUEST_TIMEOUT_SECONDS: float | None = None
DEFAULT_INTERRUPT_GRACE_SECONDS = 5.0
DEFAULT_RESUME_TIMEOUT_SECONDS = 15.0
STOP_INTERRUPT_REASON = "interrupted by /stop"
JSONRPC_INTERNAL_ERROR = -32603
JSONRPC_METHOD_NOT_FOUND = -32601
LOGGER = logging.getLogger("openrelay.backends.codex_adapter.app_server")
RequestId: TypeAlias = int | str


class InterruptedError(RuntimeError):
    pass


@dataclass(slots=True)
class CodexThreadSummary:
    thread_id: str
    preview: str = ""
    cwd: str = ""
    updated_at: str = ""
    status: str = ""
    name: str = ""


@dataclass(slots=True)
class CodexThreadMessage:
    role: str
    text: str


@dataclass(slots=True)
class CodexThreadDetails:
    thread_id: str
    preview: str = ""
    cwd: str = ""
    updated_at: str = ""
    status: str = ""
    name: str = ""
    messages: tuple[CodexThreadMessage, ...] = ()


def _normalize_thread_status(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("type", "status", "state", "name"):
            normalized = str(value.get(key) or "").strip()
            if normalized:
                return normalized
        compact = json.dumps(value, ensure_ascii=False, separators=(",", ":")).strip()
        return compact
    if isinstance(value, list):
        parts = [_normalize_thread_status(item) for item in value]
        return " / ".join(part for part in parts if part).strip()
    return str(value or "").strip()


def build_cancel_reset_reason(method: str) -> str:
    return f"Codex app-server request {method} cancelled by /stop before response"


def coerce_request_id(value: Any) -> RequestId:
    if isinstance(value, (int, str)):
        return value
    raise TypeError(f"unsupported JSON-RPC request id: {value!r}")


def _normalize_thread_summary(payload: dict[str, Any]) -> CodexThreadSummary:
    return CodexThreadSummary(
        thread_id=str(payload.get("id") or ""),
        preview=str(payload.get("preview") or "").strip(),
        cwd=str(payload.get("cwd") or "").strip(),
        updated_at=str(payload.get("updatedAt") or "").strip(),
        status=_normalize_thread_status(payload.get("status")),
        name=str(payload.get("name") or "").strip(),
    )


def _collect_text_fragments(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            parts.extend(_collect_text_fragments(item))
        return parts
    if not isinstance(value, dict):
        return []
    parts: list[str] = []
    for key in ("text", "content", "summary"):
        parts.extend(_collect_text_fragments(value.get(key)))
    return parts


def _extract_input_text(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type in {"text", "inputText"}:
            parts.extend(_collect_text_fragments(item.get("text") or item.get("content")))
            continue
        if item_type == "localImage":
            path = str(item.get("path") or "").strip()
            if path:
                parts.append(f"[image] {path}")
    return "\n".join(part for part in parts if part).strip()


def _extract_assistant_text(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type in {"agentMessage", "message"}:
            parts.extend(_collect_text_fragments(item.get("text") or item.get("content")))
            continue
        if item_type == "reasoning":
            parts.extend(_collect_text_fragments(item.get("summary")))
            if not parts:
                parts.extend(_collect_text_fragments(item.get("content")))
            continue
        if item_type == "plan":
            parts.extend(_collect_text_fragments(item.get("text") or item.get("content")))
    return "\n".join(part for part in parts if part).strip()


def _normalize_thread_details(payload: dict[str, Any]) -> CodexThreadDetails:
    summary = _normalize_thread_summary(payload)
    messages: list[CodexThreadMessage] = []
    turns = payload.get("turns")
    if isinstance(turns, list):
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            user_text = _extract_input_text(turn.get("input"))
            if user_text:
                messages.append(CodexThreadMessage(role="user", text=user_text))
            assistant_text = _extract_assistant_text(turn.get("items"))
            if assistant_text:
                messages.append(CodexThreadMessage(role="assistant", text=assistant_text))
    return CodexThreadDetails(
        thread_id=summary.thread_id,
        preview=summary.preview,
        cwd=summary.cwd,
        updated_at=summary.updated_at,
        status=summary.status,
        name=summary.name,
        messages=tuple(messages),
    )


class CodexAppServerClient:
    _instances: set["CodexAppServerClient"] = set()

    def __init__(
        self,
        codex_path: str,
        workspace_root: Path,
        sqlite_home: Path,
        model: str,
        safety_mode: str,
        *,
        request_timeout_seconds: float | None = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        interrupt_grace_seconds: float = DEFAULT_INTERRUPT_GRACE_SECONDS,
        resume_timeout_seconds: float = DEFAULT_RESUME_TIMEOUT_SECONDS,
    ):
        self.codex_path = codex_path
        self.workspace_root = workspace_root
        self.sqlite_home = sqlite_home
        self.model = model
        self.safety_mode = safety_mode
        self.request_timeout_seconds = self._normalize_request_timeout(request_timeout_seconds)
        self.interrupt_grace_seconds = interrupt_grace_seconds
        self.resume_timeout_seconds = resume_timeout_seconds
        self.process: Process | None = None
        self.stderr_text: str = ""
        self.pending_requests: dict[RequestId, asyncio.Future[Any]] = {}
        self.active_turns: set[object] = set()
        self.thread_registry: set[str] = set()
        self._ready_task: asyncio.Task[None] | None = None
        self._next_request_id = 1
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._wait_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._reset_lock = asyncio.Lock()
        self._instances.add(self)

    def _normalize_request_timeout(self, seconds: float | None) -> float | None:
        if seconds is None:
            return None
        return seconds if seconds > 0 else None

    def _format_timeout(self, seconds: float) -> str:
        if float(seconds).is_integer():
            return f"{int(seconds)}s"
        return f"{seconds:.2f}s"

    def _build_initialize_params(self) -> dict[str, Any]:
        return {
            "clientInfo": {"name": "openrelay", "version": "0.1.0"},
            "capabilities": {"experimentalApi": False},
        }

    async def _write_message(self, payload: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("Codex app-server is not running")
        raw = json.dumps(payload, ensure_ascii=False) + "\n"
        self.process.stdin.write(raw.encode("utf-8"))
        await self.process.stdin.drain()

    async def _send_server_result(self, request_id: RequestId, result: dict[str, Any]) -> None:
        await self._write_message({"id": request_id, "result": result})

    async def _send_server_error(self, request_id: RequestId, code: int, message: str, data: Any = None) -> None:
        payload: dict[str, Any] = {"id": request_id, "error": {"code": code, "message": message}}
        if data is not None:
            payload["error"]["data"] = data
        await self._write_message(payload)

    def _format_rpc_error(self, error: Any) -> str:
        if not isinstance(error, dict):
            return str(error)
        message = str(error.get("message") or "Codex app-server request failed")
        code = error.get("code")
        if isinstance(code, int):
            return f"{message} (code {code})"
        return message

    async def _handle_server_request(self, request_id: RequestId, method: str, params: dict[str, Any]) -> None:
        if method == "item/commandExecution/requestApproval":
            await self._send_server_result(request_id, {"decision": "decline"})
            return
        if method == "item/fileChange/requestApproval":
            await self._send_server_result(request_id, {"decision": "decline"})
            return
        if method == "item/permissions/requestApproval":
            await self._send_server_result(request_id, {"permissions": {}})
            return
        if method == "item/tool/requestUserInput":
            await self._send_server_result(request_id, {"answers": {}})
            return
        if method == "mcpServer/elicitation/request":
            await self._send_server_result(request_id, {"action": "decline"})
            return
        if method == "item/tool/call":
            tool_name = str(params.get("tool") or "unknown")
            await self._send_server_result(
                request_id,
                {
                    "success": False,
                    "contentItems": [
                        {
                            "type": "inputText",
                            "text": f"openrelay does not support dynamic tool calls ({tool_name})",
                        }
                    ],
                },
            )
            return
        if method in {"applyPatchApproval", "execCommandApproval"}:
            await self._send_server_result(request_id, {"decision": "denied"})
            return
        await self._send_server_error(
            request_id,
            JSONRPC_METHOD_NOT_FOUND,
            f"openrelay does not support server request method {method}",
        )

    async def _terminate_process(self, process: Process | None) -> None:
        if process is None:
            return
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

    async def _reset(self, reason: str) -> None:
        error = RuntimeError(reason)
        async with self._reset_lock:
            async with self._lock:
                process = self.process
                self.process = None
                self._ready_task = None
            self.thread_registry.clear()
            for future in list(self.pending_requests.values()):
                if not future.done():
                    future.set_exception(error)
            self.pending_requests.clear()
            for subscriber in list(self.active_turns):
                future = getattr(subscriber, "future", None)
                if future is not None and not future.done():
                    future.set_exception(error)
            self.active_turns.clear()
            await self._terminate_process(process)

    async def ensure_ready(self) -> None:
        async with self._lock:
            if self._ready_task is None:
                self._ready_task = asyncio.create_task(self._start())
            ready_task = self._ready_task
        await ready_task

    async def _start(self) -> None:
        env = self._build_process_env()
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
        assert self.process.stdout is not None
        assert self.process.stderr is not None
        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())
        self._wait_task = asyncio.create_task(self._watch_process())
        await self.request("initialize", self._build_initialize_params())

    def _build_process_env(self) -> dict[str, str]:
        env = build_subprocess_env("codex")
        env["CODEX_SQLITE_HOME"] = str(self.sqlite_home)
        return env

    async def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        while True:
            line = await self.process.stdout.readline()
            if not line:
                return
            raw = line.decode("utf-8", errors="replace").strip()
            if not raw:
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            try:
                await self._handle_message(message)
            except Exception:
                LOGGER.exception("failed to handle Codex app-server message: %s", raw)

    async def _read_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        while True:
            line = await self.process.stderr.readline()
            if not line:
                return
            self.stderr_text += line.decode("utf-8", errors="replace")

    async def _watch_process(self) -> None:
        assert self.process is not None
        code = await self.process.wait()
        error = RuntimeError(self.stderr_text.strip() or f"codex app-server exited with code {code}")
        self.thread_registry.clear()
        async with self._lock:
            self._ready_task = None
            self.process = None
        for future in list(self.pending_requests.values()):
            if not future.done():
                future.set_exception(error)
        self.pending_requests.clear()
        for subscriber in list(self.active_turns):
            future = getattr(subscriber, "future", None)
            if future is not None and not future.done():
                future.set_exception(error)
        self.active_turns.clear()

    async def _handle_message(self, message: dict[str, Any]) -> None:
        if "id" in message and "method" not in message and ("result" in message or "error" in message):
            request_id = coerce_request_id(message["id"])
            future = self.pending_requests.pop(request_id, None)
            if future is None or future.done():
                return
            if "error" in message:
                future.set_exception(RuntimeError(self._format_rpc_error(message["error"])))
            else:
                future.set_result(message.get("result"))
            return
        if "id" in message:
            request_id = coerce_request_id(message["id"])
            method = message.get("method")
            if not isinstance(method, str):
                await self._send_server_error(request_id, JSONRPC_INTERNAL_ERROR, "invalid JSON-RPC request")
                return
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            for subscriber in list(self.active_turns):
                if await subscriber.handle_server_request(self, request_id, method, params):
                    return
            try:
                await self._handle_server_request(request_id, method, params)
            except Exception as exc:
                LOGGER.exception("failed to handle Codex server request %s", method)
                await self._send_server_error(request_id, JSONRPC_INTERNAL_ERROR, str(exc))
            return
        method = message.get("method")
        if not isinstance(method, str):
            return
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        for subscriber in list(self.active_turns):
            await subscriber.handle_notification(self, method, params)
            if getattr(subscriber, "done", False):
                self.active_turns.discard(subscriber)

    async def request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        cancel_event: asyncio.Event | None = None,
        reset_on_cancel: bool = False,
        cancel_reason: str = STOP_INTERRUPT_REASON,
    ) -> Any:
        if self.process is None:
            await self.ensure_ready()
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("Codex app-server is not running")
        request_id = self._next_request_id
        self._next_request_id += 1
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self.pending_requests[request_id] = future
        if cancel_event is not None and cancel_event.is_set():
            self.pending_requests.pop(request_id, None)
            future.cancel()
            raise InterruptedError(cancel_reason)
        await self._write_message({"id": request_id, "method": method, "params": params})

        async def wait_for_response() -> Any:
            if self.request_timeout_seconds is None:
                return await future
            return await asyncio.wait_for(asyncio.shield(future), timeout=self.request_timeout_seconds)

        response_task = asyncio.create_task(wait_for_response())
        cancel_task: asyncio.Task[bool] | None = None
        if cancel_event is not None:
            cancel_task = asyncio.create_task(cancel_event.wait())
        try:
            if cancel_task is None:
                return await response_task
            done, _ = await asyncio.wait({response_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED)
            if response_task in done:
                return await response_task
            self.pending_requests.pop(request_id, None)
            future.cancel()
            response_task.cancel()
            if reset_on_cancel:
                await self._reset(build_cancel_reset_reason(method))
            raise InterruptedError(cancel_reason)
        except asyncio.TimeoutError as exc:
            self.pending_requests.pop(request_id, None)
            reason = f"Codex app-server request {method} timed out after {self._format_timeout(self.request_timeout_seconds)}"
            await self._reset(reason)
            raise RuntimeError(reason) from exc
        except asyncio.CancelledError:
            self.pending_requests.pop(request_id, None)
            future.cancel()
            raise
        finally:
            response_task.cancel()
            if cancel_task is not None:
                cancel_task.cancel()

    async def list_threads(self, limit: int = 20) -> tuple[list[CodexThreadSummary], str]:
        result = await self.request("thread/list", {"limit": max(limit, 1)})
        rows = result.get("data") if isinstance(result, dict) else []
        if not isinstance(rows, list):
            rows = []
        return ([_normalize_thread_summary(item) for item in rows if isinstance(item, dict)], str(result.get("nextCursor") or ""))

    async def read_thread(self, thread_id: str, *, include_turns: bool = True) -> CodexThreadDetails:
        result = await self.request("thread/read", {"threadId": thread_id, "includeTurns": include_turns})
        thread = result.get("thread") if isinstance(result, dict) and isinstance(result.get("thread"), dict) else {}
        return _normalize_thread_details(thread)

    async def compact_thread(self, thread_id: str) -> dict[str, Any]:
        result = await self.request("thread/compact/start", {"threadId": thread_id})
        return result if isinstance(result, dict) else {}

    async def shutdown(self) -> None:
        process = self.process
        self.process = None
        self._instances.discard(self)
        if process is None:
            return
        async with self._lock:
            self._ready_task = None
        await self._terminate_process(process)

    @classmethod
    async def shutdown_all(cls) -> None:
        for client in list(cls._instances):
            await client.shutdown()
        cls._instances.clear()
