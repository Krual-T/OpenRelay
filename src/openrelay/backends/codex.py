from __future__ import annotations

import asyncio
import json
import logging
from asyncio.subprocess import PIPE, Process
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias

from openrelay.backends.base import Backend, BackendContext, build_subprocess_env, safety_to_codex_approval
from openrelay.models import BackendReply, SessionRecord


DEFAULT_REQUEST_TIMEOUT_SECONDS: float | None = None
DEFAULT_INTERRUPT_GRACE_SECONDS = 5.0
DEFAULT_RESUME_TIMEOUT_SECONDS = 15.0
STOP_INTERRUPT_REASON = "interrupted by /stop"
JSONRPC_INTERNAL_ERROR = -32603
JSONRPC_METHOD_NOT_FOUND = -32601
LOGGER = logging.getLogger("openrelay.backends.codex")
RequestId: TypeAlias = int | str


class InterruptedError(RuntimeError):
    pass


def build_cancel_reset_reason(method: str) -> str:
    return f"Codex app-server request {method} cancelled by /stop before response"


def coerce_request_id(value: Any) -> RequestId:
    if isinstance(value, (int, str)):
        return value
    raise TypeError(f"unsupported JSON-RPC request id: {value!r}")


def combine_indexed_text(parts_by_index: dict[int, str]) -> str:
    parts: list[str] = []
    for index in sorted(parts_by_index):
        text = str(parts_by_index.get(index) or "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()


@dataclass(slots=True)
class ReasoningItemState:
    content_by_index: dict[int, str] = field(default_factory=dict)
    summary_by_index: dict[int, str] = field(default_factory=dict)

    def append_content(self, index: int, delta: str) -> None:
        self.content_by_index[index] = f"{self.content_by_index.get(index, '')}{delta or ''}"

    def append_summary(self, index: int, delta: str) -> None:
        self.summary_by_index[index] = f"{self.summary_by_index.get(index, '')}{delta or ''}"

    def seed_content(self, parts: list[str]) -> None:
        for index, part in enumerate(parts):
            self.content_by_index[index] = str(part)

    def seed_summary(self, parts: list[str]) -> None:
        for index, part in enumerate(parts):
            self.summary_by_index[index] = str(part)

    def text(self) -> str:
        return combine_indexed_text(self.summary_by_index) or combine_indexed_text(self.content_by_index)


@dataclass(slots=True, eq=False)
class CodexTurn:
    thread_id: str
    on_partial_text: Any = None
    on_progress: Any = None
    on_server_request: Any = None
    turn_id: str = ""
    final_text: str = ""
    interrupted: bool = False
    interrupt_message: str = "interrupted by user"
    interrupt_sent: bool = False
    done: bool = False
    agent_messages: list[str] = field(default_factory=list)
    command_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    command_output_by_id: dict[str, str] = field(default_factory=dict)
    file_change_output_by_id: dict[str, str] = field(default_factory=dict)
    reasoning_by_id: dict[str, ReasoningItemState] = field(default_factory=dict)
    reasoning_order: list[str] = field(default_factory=list)
    agent_text_by_id: dict[str, str] = field(default_factory=dict)
    plan_text_by_id: dict[str, str] = field(default_factory=dict)
    usage: dict[str, Any] | None = None
    future: asyncio.Future[BackendReply] | None = None

    def __post_init__(self) -> None:
        self.future = asyncio.get_running_loop().create_future()

    def _remember_reasoning_item(self, item_id: str) -> None:
        if item_id and item_id not in self.reasoning_order:
            self.reasoning_order.append(item_id)

    def _reasoning_state(self, item_id: str) -> ReasoningItemState:
        self._remember_reasoning_item(item_id)
        state = self.reasoning_by_id.get(item_id)
        if state is None:
            state = ReasoningItemState()
            self.reasoning_by_id[item_id] = state
        return state

    def _combined_reasoning_text(self) -> str:
        parts: list[str] = []
        for item_id in self.reasoning_order:
            text = self._reasoning_state(item_id).text().strip()
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()

    def matches(self, thread_id: str, turn_id: str = "") -> bool:
        if thread_id != self.thread_id:
            return False
        if not turn_id:
            return True
        return not self.turn_id or self.turn_id == turn_id

    async def interrupt(self, client: "CodexAppServerClient", reason: str = "interrupted by user") -> None:
        self.interrupted = True
        self.interrupt_message = reason
        if not self.turn_id or self.interrupt_sent:
            return
        self.interrupt_sent = True
        try:
            await client.request("turn/interrupt", {"threadId": self.thread_id, "turnId": self.turn_id})
        except Exception:
            return

    async def set_turn_id(self, client: "CodexAppServerClient", turn_id: str) -> None:
        self.turn_id = turn_id or self.turn_id
        if self.interrupted and self.turn_id and not self.interrupt_sent:
            self.interrupt_sent = True
            try:
                await client.request("turn/interrupt", {"threadId": self.thread_id, "turnId": self.turn_id})
            except Exception:
                return

    async def _emit_progress(self, event: dict[str, Any]) -> None:
        if self.on_progress is not None:
            await self.on_progress(event)

    async def _emit_partial_text(self, text: str) -> None:
        if not text:
            return
        self.final_text = text
        await self._emit_progress({"type": "assistant.partial", "text": text})
        if self.on_partial_text is not None:
            await self.on_partial_text(text)

    def _extract_search(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(item.get("id") or ""),
            "query": str(item.get("query") or ""),
            "action": item.get("action") if isinstance(item.get("action"), dict) else {},
        }

    async def _handle_turn_started(self, client: "CodexAppServerClient", params: dict[str, Any]) -> None:
        turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
        await self.set_turn_id(client, str(turn.get("id") or self.turn_id))

    async def _handle_agent_message_delta(self, params: dict[str, Any]) -> None:
        item_id = str(params.get("itemId") or "")
        text = f"{self.agent_text_by_id.get(item_id, '')}{params.get('delta') or ''}"
        self.agent_text_by_id[item_id] = text
        await self._emit_partial_text(text)

    async def _handle_reasoning_text_delta(self, params: dict[str, Any]) -> None:
        item_id = str(params.get("itemId") or "")
        content_index = int(params.get("contentIndex") or 0)
        reasoning = self._reasoning_state(item_id)
        reasoning.append_content(content_index, str(params.get("delta") or ""))
        await self._emit_progress({"type": "reasoning.delta", "text": self._combined_reasoning_text()})

    async def _handle_reasoning_summary_delta(self, params: dict[str, Any]) -> None:
        item_id = str(params.get("itemId") or "")
        summary_index = int(params.get("summaryIndex") or 0)
        reasoning = self._reasoning_state(item_id)
        reasoning.append_summary(summary_index, str(params.get("delta") or ""))
        await self._emit_progress({"type": "reasoning.delta", "text": self._combined_reasoning_text()})

    async def _handle_command_output_delta(self, params: dict[str, Any]) -> None:
        item_id = str(params.get("itemId") or "")
        self.command_output_by_id[item_id] = f"{self.command_output_by_id.get(item_id, '')}{params.get('delta') or ''}"

    async def _handle_item_started(self, params: dict[str, Any]) -> None:
        item = params.get("item") if isinstance(params.get("item"), dict) else {}
        item_type = item.get("type")
        if item_type == "reasoning":
            self._reasoning_state(str(item.get("id") or ""))
            await self._emit_progress({"type": "reasoning.started"})
            return
        if item_type == "webSearch":
            await self._emit_progress({"type": "web_search.started", "search": self._extract_search(item)})
            return
        if item_type == "commandExecution":
            item_id = str(item.get("id") or "")
            command = {
                "id": item_id,
                "command": str(item.get("command") or ""),
                "outputPreview": self.command_output_by_id.get(item_id, ""),
                "exitCode": None,
            }
            self.command_by_id[item_id] = command
            await self._emit_progress({"type": "command.started", "command": command})

    async def _handle_item_completed(self, params: dict[str, Any]) -> None:
        item = params.get("item") if isinstance(params.get("item"), dict) else {}
        item_type = item.get("type")
        if item_type == "agentMessage":
            item_id = str(item.get("id") or "")
            text = str(item.get("text") or self.agent_text_by_id.get(item_id, "")).strip()
            if text:
                self.final_text = text
                self.agent_messages.append(text)
                await self._emit_progress({"type": "agent.message", "text": text})
            return
        if item_type == "reasoning":
            item_id = str(item.get("id") or "")
            reasoning = self._reasoning_state(item_id)
            summary = item.get("summary")
            content = item.get("content")
            if isinstance(summary, list):
                reasoning.seed_summary([str(part) for part in summary])
            if isinstance(content, list):
                reasoning.seed_content([str(part) for part in content])
            text = self._combined_reasoning_text() or reasoning.text()
            await self._emit_progress({"type": "reasoning.completed", "text": text})
            return
        if item_type == "webSearch":
            await self._emit_progress({"type": "web_search.completed", "search": self._extract_search(item)})
            return
        if item_type == "commandExecution":
            item_id = str(item.get("id") or "")
            previous = self.command_by_id.get(item_id, {})
            command = {
                "id": item_id,
                "command": str(item.get("command") or previous.get("command") or ""),
                "outputPreview": str(
                    item.get("aggregatedOutput")
                    or self.command_output_by_id.get(item_id, "")
                    or previous.get("outputPreview")
                    or ""
                ),
                "exitCode": item.get("exitCode") if isinstance(item.get("exitCode"), int) else None,
            }
            self.command_by_id[item_id] = command
            await self._emit_progress({"type": "command.completed", "command": command})
            return
        if item_type == "plan":
            item_id = str(item.get("id") or "")
            text = str(item.get("text") or self.plan_text_by_id.get(item_id, "")).strip()
            if text:
                self.plan_text_by_id[item_id] = text
                await self._emit_progress({"type": "plan.completed", "text": text})

    async def _handle_token_usage_updated(self, params: dict[str, Any]) -> None:
        token_usage = params.get("tokenUsage") if isinstance(params.get("tokenUsage"), dict) else {}
        last = (
            token_usage.get("last")
            if isinstance(token_usage.get("last"), dict)
            else token_usage.get("total")
            if isinstance(token_usage.get("total"), dict)
            else {}
        )
        self.usage = {
            "input_tokens": last.get("inputTokens"),
            "cached_input_tokens": last.get("cachedInputTokens"),
            "output_tokens": last.get("outputTokens"),
            "reasoning_output_tokens": last.get("reasoningOutputTokens"),
            "total_tokens": last.get("totalTokens"),
            "model_context_window": token_usage.get("modelContextWindow"),
        }

    async def _handle_error(self, params: dict[str, Any]) -> None:
        if params.get("willRetry"):
            return
        self.done = True
        if self.future is not None and not self.future.done():
            error = params.get("error") if isinstance(params.get("error"), dict) else {}
            self.future.set_exception(RuntimeError(str(error.get("message") or params)))

    async def _handle_turn_completed(self, params: dict[str, Any]) -> None:
        turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
        status = str(turn.get("status") or "")
        self.done = True
        await self._emit_progress({"type": "turn.completed", "usage": self.usage})
        if status == "completed":
            reply = BackendReply(
                text=(self.final_text or (self.agent_messages[-1] if self.agent_messages else "")).strip(),
                native_session_id=self.thread_id,
                metadata={"usage": self.usage or {}},
            )
            if self.future is not None and not self.future.done():
                self.future.set_result(reply)
            return
        if status == "interrupted":
            if self.future is not None and not self.future.done():
                self.future.set_exception(InterruptedError(self.interrupt_message))
            return
        message = str(turn.get("error", {}).get("message") or f"Turn {status or 'failed'}")
        if self.future is not None and not self.future.done():
            self.future.set_exception(RuntimeError(message))

    async def handle_notification(self, client: "CodexAppServerClient", method: str, params: dict[str, Any]) -> None:
        if self.done:
            return
        thread = params.get("thread") if isinstance(params.get("thread"), dict) else {}
        turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
        thread_id = str(params.get("threadId") or thread.get("id") or "")
        turn_id = str(params.get("turnId") or turn.get("id") or "")
        if not self.matches(thread_id, turn_id):
            return

        if method == "turn/started":
            await self._handle_turn_started(client, params)
            return
        if method == "item/agentMessage/delta":
            await self._handle_agent_message_delta(params)
            return
        if method == "item/reasoning/textDelta":
            await self._handle_reasoning_text_delta(params)
            return
        if method == "item/reasoning/summaryTextDelta":
            await self._handle_reasoning_summary_delta(params)
            return
        if method == "item/reasoning/summaryPartAdded":
            self._reasoning_state(str(params.get("itemId") or ""))
            return
        if method == "item/plan/delta":
            item_id = str(params.get("itemId") or "")
            text = f"{self.plan_text_by_id.get(item_id, '')}{params.get('delta') or ''}"
            self.plan_text_by_id[item_id] = text
            await self._emit_progress({"type": "plan.delta", "text": text})
            return
        if method == "item/commandExecution/outputDelta":
            await self._handle_command_output_delta(params)
            return
        if method == "item/commandExecution/terminalInteraction":
            await self._emit_progress(
                {
                    "type": "command.terminal",
                    "interaction": {
                        "itemId": str(params.get("itemId") or ""),
                        "processId": str(params.get("processId") or ""),
                        "stdin": str(params.get("stdin") or ""),
                    },
                }
            )
            return
        if method == "item/fileChange/outputDelta":
            item_id = str(params.get("itemId") or "")
            self.file_change_output_by_id[item_id] = f"{self.file_change_output_by_id.get(item_id, '')}{params.get('delta') or ''}"
            return
        if method == "turn/plan/updated":
            await self._emit_progress(
                {
                    "type": "plan.updated",
                    "plan": params.get("plan") if isinstance(params.get("plan"), list) else [],
                    "explanation": params.get("explanation"),
                }
            )
            return
        if method == "item/mcpToolCall/progress":
            await self._emit_progress(
                {
                    "type": "mcp_tool.progress",
                    "progress": {
                        "itemId": str(params.get("itemId") or ""),
                        "content": params.get("content"),
                    },
                }
            )
            return
        if method == "serverRequest/resolved":
            await self._emit_progress(
                {
                    "type": "server_request.resolved",
                    "requestId": params.get("requestId"),
                    "threadId": str(params.get("threadId") or ""),
                }
            )
            return
        if method == "item/started":
            await self._handle_item_started(params)
            return
        if method == "item/completed":
            await self._handle_item_completed(params)
            return
        if method == "thread/tokenUsage/updated":
            await self._handle_token_usage_updated(params)
            return
        if method == "error":
            await self._handle_error(params)
            return
        if method == "turn/completed":
            await self._handle_turn_completed(params)

    async def handle_server_request(
        self,
        client: "CodexAppServerClient",
        request_id: RequestId,
        method: str,
        params: dict[str, Any],
    ) -> bool:
        if self.done:
            return False
        thread_id = str(params.get("threadId") or "")
        turn_id = str(params.get("turnId") or "")
        if not self.matches(thread_id, turn_id):
            return False
        if self.on_server_request is None:
            return False
        try:
            result = await self.on_server_request(method, params)
        except NotImplementedError:
            return False
        await client._send_server_result(request_id, result if isinstance(result, dict) else {})
        return True


class CodexAppServerClient:
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
        self.active_turns: set[CodexTurn] = set()
        self.thread_registry: set[str] = set()
        self._ready_task: asyncio.Task[None] | None = None
        self._next_request_id = 1
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._wait_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._reset_lock = asyncio.Lock()

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

    def _build_thread_params(self, session: SessionRecord) -> dict[str, Any]:
        params = {
            "cwd": session.cwd,
            "model": session.model_override or self.model or None,
            "sandbox": session.safety_mode,
            "approvalPolicy": safety_to_codex_approval(session.safety_mode),
        }
        return {key: value for key, value in params.items() if value not in {None, ""}}

    def _build_turn_start_params(
        self,
        session: SessionRecord,
        thread_id: str,
        prompt: str,
        local_image_paths: tuple[str, ...],
    ) -> dict[str, Any]:
        return {
            "threadId": thread_id,
            "cwd": session.cwd,
            "approvalPolicy": safety_to_codex_approval(session.safety_mode),
            **({"model": session.model_override} if session.model_override else {}),
            "input": self._build_turn_input(prompt, local_image_paths),
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
            for turn in list(self.active_turns):
                if turn.future is not None and not turn.future.done():
                    turn.future.set_exception(error)
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
        for turn in list(self.active_turns):
            if turn.future is not None and not turn.future.done():
                turn.future.set_exception(error)
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
            for turn in list(self.active_turns):
                if await turn.handle_server_request(self, request_id, method, params):
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
        for turn in list(self.active_turns):
            await turn.handle_notification(self, method, params)
            if turn.done:
                self.active_turns.discard(turn)

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

    async def ensure_thread(self, session: SessionRecord, context: BackendContext) -> str:
        await self.ensure_ready()
        params = self._build_thread_params(session)
        if session.native_session_id:
            thread_id = session.native_session_id
            if thread_id not in self.thread_registry:
                try:
                    await asyncio.wait_for(
                        self.request(
                            "thread/resume",
                            {**params, "threadId": thread_id},
                            cancel_event=context.cancel_event,
                            reset_on_cancel=True,
                        ),
                        timeout=self.resume_timeout_seconds,
                    )
                    self.thread_registry.add(thread_id)
                    if context.on_progress is not None:
                        await context.on_progress({"type": "thread.started", "threadId": thread_id})
                except InterruptedError:
                    raise
                except asyncio.TimeoutError:
                    LOGGER.warning(
                        "thread/resume timed out for native_session_id=%s; resetting client and starting fresh thread",
                        thread_id,
                    )
                    await self._reset(
                        "Codex app-server thread/resume timed out after "
                        f"{self._format_timeout(self.resume_timeout_seconds)}"
                    )
                except Exception as exc:
                    LOGGER.warning(
                        "thread/resume failed for native_session_id=%s; starting fresh thread: %s",
                        thread_id,
                        exc,
                    )
                else:
                    return thread_id
        result = await self.request(
            "thread/start",
            params,
            cancel_event=context.cancel_event,
            reset_on_cancel=True,
        )
        thread_id = str(result.get("thread", {}).get("id") or "")
        if not thread_id:
            raise RuntimeError("Codex app-server returned no thread id")
        self.thread_registry.add(thread_id)
        if context.on_progress is not None:
            await context.on_progress({"type": "thread.started", "threadId": thread_id})
        return thread_id

    async def run_turn(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        if context.on_progress is not None:
            await context.on_progress({"type": "run.started"})
        thread_id = await self.ensure_thread(session, context)
        turn = CodexTurn(
            thread_id=thread_id,
            on_partial_text=context.on_partial_text,
            on_progress=context.on_progress,
            on_server_request=context.on_server_request,
        )
        self.active_turns.add(turn)
        watcher: asyncio.Task[None] | None = None
        try:
            result = await self.request(
                "turn/start",
                self._build_turn_start_params(session, thread_id, prompt, context.local_image_paths),
                cancel_event=context.cancel_event,
                reset_on_cancel=True,
            )
            await turn.set_turn_id(self, str(result.get("turn", {}).get("id") or ""))

            async def cancel_watcher() -> None:
                if context.cancel_event is None:
                    return
                await context.cancel_event.wait()
                await turn.interrupt(self, STOP_INTERRUPT_REASON)
                if turn.future is None or turn.future.done():
                    return
                try:
                    await asyncio.wait_for(asyncio.shield(turn.future), timeout=self.interrupt_grace_seconds)
                except asyncio.TimeoutError:
                    reason = (
                        "Codex app-server did not stop after interrupt within "
                        f"{self._format_timeout(self.interrupt_grace_seconds)}"
                    )
                    await self._reset(reason)
                except Exception:
                    return

            if context.cancel_event is not None and context.cancel_event.is_set():
                await turn.interrupt(self, STOP_INTERRUPT_REASON)
            watcher = asyncio.create_task(cancel_watcher())
            reply = await turn.future
            if not reply.text.strip():
                raise RuntimeError("Codex app-server returned no agent text")
            return reply
        finally:
            if watcher is not None:
                watcher.cancel()
            self.active_turns.discard(turn)

    def _build_turn_input(self, prompt: str, local_image_paths: tuple[str, ...]) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        if prompt.strip():
            items.append({"type": "text", "text": prompt})
        for path in local_image_paths:
            items.append({"type": "localImage", "path": path})
        return items

    async def shutdown(self) -> None:
        process = self.process
        self.process = None
        if process is None:
            return
        async with self._lock:
            self._ready_task = None
        await self._terminate_process(process)


class CodexBackend(Backend):
    name = "codex"
    _clients: dict[tuple[str, str, str], CodexAppServerClient] = {}

    def __init__(
        self,
        codex_path: str,
        default_model: str,
        *,
        sqlite_home: Path,
        request_timeout_seconds: float | None = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        interrupt_grace_seconds: float = DEFAULT_INTERRUPT_GRACE_SECONDS,
        resume_timeout_seconds: float = DEFAULT_RESUME_TIMEOUT_SECONDS,
    ):
        self.codex_path = codex_path
        self.default_model = default_model
        self.sqlite_home = sqlite_home
        self.request_timeout_seconds = request_timeout_seconds
        self.interrupt_grace_seconds = interrupt_grace_seconds
        self.resume_timeout_seconds = resume_timeout_seconds

    def _client_key(self, session: SessionRecord, context: BackendContext) -> tuple[str, str, str]:
        return (
            self.codex_path,
            str(context.workspace_root),
            session.session_id,
        )

    def _get_client(self, session: SessionRecord, context: BackendContext) -> CodexAppServerClient:
        key = self._client_key(session, context)
        client = self._clients.get(key)
        if client is None:
            client = CodexAppServerClient(
                codex_path=self.codex_path,
                workspace_root=context.workspace_root,
                sqlite_home=self.sqlite_home,
                model=session.model_override or self.default_model,
                safety_mode=session.safety_mode,
                request_timeout_seconds=self.request_timeout_seconds,
                interrupt_grace_seconds=self.interrupt_grace_seconds,
                resume_timeout_seconds=self.resume_timeout_seconds,
            )
            self._clients[key] = client
        return client

    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        client = self._get_client(session, context)
        return await client.run_turn(session, prompt, context)

    @classmethod
    async def shutdown_all(cls) -> None:
        for client in list(cls._clients.values()):
            await client.shutdown()
        cls._clients.clear()
