from __future__ import annotations

import asyncio
import json
import logging
from asyncio.subprocess import PIPE, Process
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias

from openrelay.agent_runtime import (
    ApprovalResolvedEvent,
    AssistantCompletedEvent,
    AssistantDeltaEvent,
    BackendNoticeEvent,
    PlanUpdatedEvent,
    ReasoningDeltaEvent,
    RuntimeEvent,
    SessionStartedEvent,
    ToolCompletedEvent,
    ToolProgressEvent,
    ToolStartedEvent,
    TurnCompletedEvent,
    TurnFailedEvent,
    TurnInterruptedEvent,
    TurnStartedEvent,
    UsageUpdatedEvent,
)
from openrelay.backends.base import Backend, BackendContext, build_subprocess_env, safety_to_codex_approval
from openrelay.backends.codex_adapter.mapper import CodexProtocolMapper
from openrelay.core import BackendReply, SessionRecord


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


def _normalize_thread_summary(payload: dict[str, Any]) -> CodexThreadSummary:
    return CodexThreadSummary(
        thread_id=str(payload.get("id") or ""),
        preview=str(payload.get("preview") or "").strip(),
        cwd=str(payload.get("cwd") or "").strip(),
        updated_at=str(payload.get("updatedAt") or "").strip(),
        status=str(payload.get("status") or "").strip(),
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


def _normalize_event_item_type(item_type: object) -> str:
    normalized = str(item_type or "").strip()
    if not normalized:
        return ""
    return normalized[:1].lower() + normalized[1:]


def _normalize_event_item(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized["type"] = _normalize_event_item_type(item.get("type"))
    if "summary_text" in normalized and "summary" not in normalized:
        normalized["summary"] = normalized.get("summary_text")
    if "raw_content" in normalized and "content" not in normalized:
        normalized["content"] = normalized.get("raw_content")
    if "item_id" in normalized and "id" not in normalized:
        normalized["id"] = normalized.get("item_id")
    if "output_preview" in normalized and "outputPreview" not in normalized:
        normalized["outputPreview"] = normalized.get("output_preview")
    if "aggregated_output" in normalized and "aggregatedOutput" not in normalized:
        normalized["aggregatedOutput"] = normalized.get("aggregated_output")
    if "exit_code" in normalized and "exitCode" not in normalized:
        normalized["exitCode"] = normalized.get("exit_code")
    return normalized


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
    last_delta_fingerprint: tuple[str, ...] | None = None
    last_delta_method: str = ""
    mapper: CodexProtocolMapper = field(init=False)

    def __post_init__(self) -> None:
        self.future = asyncio.get_running_loop().create_future()
        self.mapper = CodexProtocolMapper(
            session_id=self.thread_id,
            native_session_id=self.thread_id,
            turn_id=self.turn_id,
        )

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

    def _message_identity(self, params: dict[str, Any]) -> tuple[str, str]:
        msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
        thread = params.get("thread") if isinstance(params.get("thread"), dict) else {}
        turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
        thread_id = str(
            params.get("threadId")
            or thread.get("id")
            or params.get("conversationId")
            or msg.get("thread_id")
            or msg.get("threadId")
            or ""
        )
        turn_id = str(
            params.get("turnId")
            or turn.get("id")
            or msg.get("turn_id")
            or msg.get("turnId")
            or params.get("id")
            or ""
        )
        return thread_id, turn_id

    def _extract_event_item(self, params: dict[str, Any]) -> dict[str, Any]:
        item = params.get("item") if isinstance(params.get("item"), dict) else {}
        if item:
            return item
        msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
        event_item = msg.get("item") if isinstance(msg.get("item"), dict) else {}
        return _normalize_event_item(event_item)

    def _duplicate_delta_alias(self, method: str, params: dict[str, Any]) -> bool:
        msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
        delta = str(params.get("delta") or msg.get("delta") or "")
        fingerprint: tuple[str, ...] | None = None
        if method in {"item/agentMessage/delta", "codex/event/agent_message_content_delta"} and delta:
            fingerprint = (
                "agent",
                str(params.get("itemId") or msg.get("item_id") or msg.get("itemId") or ""),
                delta,
            )
        elif method in {"item/reasoning/textDelta", "codex/event/reasoning_content_delta"} and delta:
            fingerprint = (
                "reasoning.content",
                str(params.get("itemId") or msg.get("item_id") or msg.get("itemId") or ""),
                str(params.get("contentIndex") or msg.get("content_index") or msg.get("contentIndex") or 0),
                delta,
            )
        elif method in {"item/reasoning/summaryTextDelta", "codex/event/reasoning_summary_text_delta"} and delta:
            fingerprint = (
                "reasoning.summary",
                str(params.get("itemId") or msg.get("item_id") or msg.get("itemId") or ""),
                str(params.get("summaryIndex") or msg.get("summary_index") or msg.get("summaryIndex") or 0),
                delta,
            )
        if fingerprint is None:
            self.last_delta_fingerprint = None
            self.last_delta_method = ""
            return False
        is_duplicate = fingerprint == self.last_delta_fingerprint and method != self.last_delta_method
        self.last_delta_fingerprint = fingerprint
        self.last_delta_method = method
        return is_duplicate

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
        self.mapper.turn_id = self.turn_id
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

    async def _apply_runtime_event(self, event: RuntimeEvent) -> None:
        if isinstance(event, SessionStartedEvent):
            return
        if isinstance(event, TurnStartedEvent):
            self.turn_id = event.turn_id or self.turn_id
            self.mapper.turn_id = self.turn_id
            return
        if isinstance(event, AssistantDeltaEvent):
            await self._emit_partial_text(self.mapper.final_text)
            return
        if isinstance(event, AssistantCompletedEvent):
            if event.text:
                self.final_text = event.text
                self.agent_messages.append(event.text)
                await self._emit_progress({"type": "agent.message", "text": event.text})
            return
        if isinstance(event, ReasoningDeltaEvent):
            event_type = "reasoning.completed" if event.provider_payload.get("completed") else "reasoning.delta"
            await self._emit_progress({"type": event_type, "text": event.text})
            return
        if isinstance(event, BackendNoticeEvent):
            method = str(event.provider_payload.get("method") or "")
            if method == "item/plan/delta":
                await self._emit_progress({"type": "plan.delta", "text": event.message})
                return
            if method == "item/commandExecution/terminalInteraction":
                await self._emit_progress(
                    {
                        "type": "command.terminal",
                        "interaction": {
                            "itemId": str(event.provider_payload.get("item_id") or ""),
                            "processId": str(event.provider_payload.get("process_id") or ""),
                            "stdin": str(event.provider_payload.get("stdin") or ""),
                        },
                    }
                )
                return
            if event.message == "Reasoning started":
                await self._emit_progress({"type": "reasoning.started"})
            return
        if isinstance(event, PlanUpdatedEvent):
            if event.provider_payload.get("item_id"):
                text = event.steps[0].step if event.steps else ""
                if text:
                    self.plan_text_by_id[str(event.provider_payload.get("item_id") or "")] = text
                    await self._emit_progress({"type": "plan.completed", "text": text})
                return
            await self._emit_progress(
                {
                    "type": "plan.updated",
                    "plan": [{"step": step.step, "status": step.status} for step in event.steps],
                    "explanation": event.explanation,
                }
            )
            return
        if isinstance(event, ToolStartedEvent):
            await self._emit_legacy_tool_event("started", event.tool)
            return
        if isinstance(event, ToolProgressEvent):
            if event.provider_payload.get("method") == "item/mcpToolCall/progress":
                await self._emit_progress(
                    {
                        "type": "mcp_tool.progress",
                        "progress": {
                            "itemId": event.tool_id,
                            "content": event.provider_payload.get("content"),
                        },
                    }
                )
            return
        if isinstance(event, ToolCompletedEvent):
            await self._emit_legacy_tool_event("completed", event.tool)
            return
        if isinstance(event, ApprovalResolvedEvent):
            await self._emit_progress({"type": "server_request.resolved", "requestId": event.approval_id, "threadId": self.thread_id})
            return
        if isinstance(event, UsageUpdatedEvent):
            self.usage = {
                "input_tokens": event.usage.input_tokens,
                "cached_input_tokens": event.usage.cached_input_tokens,
                "output_tokens": event.usage.output_tokens,
                "reasoning_output_tokens": event.usage.reasoning_output_tokens,
                "total_tokens": event.usage.total_tokens,
                "model_context_window": event.usage.context_window,
            }
            return
        if isinstance(event, TurnCompletedEvent):
            self.done = True
            if event.final_text:
                self.final_text = event.final_text
            if event.usage is not None:
                self.usage = {
                    "input_tokens": event.usage.input_tokens,
                    "cached_input_tokens": event.usage.cached_input_tokens,
                    "output_tokens": event.usage.output_tokens,
                    "reasoning_output_tokens": event.usage.reasoning_output_tokens,
                    "total_tokens": event.usage.total_tokens,
                    "model_context_window": event.usage.context_window,
                }
            await self._emit_progress({"type": "turn.completed", "usage": self.usage})
            reply = BackendReply(
                text=(self.final_text or (self.agent_messages[-1] if self.agent_messages else "")).strip(),
                native_session_id=self.thread_id,
                metadata={"usage": self.usage or {}},
            )
            if self.future is not None and not self.future.done():
                self.future.set_result(reply)
            return
        if isinstance(event, TurnInterruptedEvent):
            self.done = True
            if self.future is not None and not self.future.done():
                self.future.set_exception(InterruptedError(self.interrupt_message))
            return
        if isinstance(event, TurnFailedEvent):
            self.done = True
            if self.future is not None and not self.future.done():
                self.future.set_exception(RuntimeError(event.message))

    async def _emit_legacy_tool_event(self, phase: str, tool: Any) -> None:
        if tool.kind == "command":
            command = {
                "id": tool.tool_id,
                "command": tool.title if tool.title != "Command" else tool.preview,
                "outputPreview": tool.detail,
                "exitCode": tool.exit_code,
            }
            self.command_by_id[tool.tool_id] = command
            await self._emit_progress({"type": f"command.{phase}", "command": command})
            return
        if tool.kind == "web_search":
            search = {
                "id": tool.tool_id,
                "query": tool.preview,
                "action": tool.provider_payload.get("action") if isinstance(tool.provider_payload, dict) else {},
            }
            await self._emit_progress({"type": f"web_search.{phase}", "search": search})
            return
        if tool.kind == "file_change":
            file_change = {
                "id": tool.tool_id,
                "status": str(tool.provider_payload.get("status") or ""),
                "changes": tool.provider_payload.get("changes") if isinstance(tool.provider_payload.get("changes"), list) else [],
            }
            await self._emit_progress({"type": f"file_change.{phase}", "file_change": file_change})
            return
        if tool.kind == "custom":
            collab = {
                "id": tool.tool_id,
                "tool": tool.title,
                "status": str(tool.provider_payload.get("status") or ""),
                "prompt": tool.preview,
                "senderThreadId": str(tool.provider_payload.get("senderThreadId") or ""),
                "receiverThreadIds": list(tool.provider_payload.get("receiverThreadIds") or []),
                "agentsStates": tool.provider_payload.get("agentsStates") if isinstance(tool.provider_payload.get("agentsStates"), dict) else {},
            }
            await self._emit_progress({"type": f"collab.{phase}", "collab": collab})

    def _extract_search(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(item.get("id") or ""),
            "query": str(item.get("query") or ""),
            "action": item.get("action") if isinstance(item.get("action"), dict) else {},
        }

    def _extract_file_change(self, item: dict[str, Any]) -> dict[str, Any]:
        changes = item.get("changes") if isinstance(item.get("changes"), list) else []
        return {
            "id": str(item.get("id") or ""),
            "status": str(item.get("status") or ""),
            "changes": [change for change in changes if isinstance(change, dict)],
        }

    def _extract_collab_tool_call(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(item.get("id") or ""),
            "tool": str(item.get("tool") or ""),
            "status": str(item.get("status") or ""),
            "prompt": str(item.get("prompt") or ""),
            "senderThreadId": str(item.get("senderThreadId") or ""),
            "receiverThreadIds": list(item.get("receiverThreadIds") or []),
            "agentsStates": item.get("agentsStates") if isinstance(item.get("agentsStates"), dict) else {},
        }

    async def _handle_turn_started(self, client: "CodexAppServerClient", params: dict[str, Any]) -> None:
        turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
        if not turn:
            msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
            turn = msg.get("turn") if isinstance(msg.get("turn"), dict) else {}
        await self.set_turn_id(client, str(turn.get("id") or self.turn_id))

    async def _handle_agent_message_delta(self, params: dict[str, Any]) -> None:
        msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
        item_id = str(params.get("itemId") or msg.get("item_id") or msg.get("itemId") or "")
        delta = str(params.get("delta") or msg.get("delta") or "")
        text = f"{self.agent_text_by_id.get(item_id, '')}{delta}"
        self.agent_text_by_id[item_id] = text
        await self._emit_partial_text(text)

    async def _handle_reasoning_text_delta(self, params: dict[str, Any]) -> None:
        msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
        item_id = str(params.get("itemId") or msg.get("item_id") or msg.get("itemId") or "")
        content_index = int(params.get("contentIndex") or msg.get("content_index") or msg.get("contentIndex") or 0)
        reasoning = self._reasoning_state(item_id)
        reasoning.append_content(content_index, str(params.get("delta") or msg.get("delta") or ""))
        await self._emit_progress({"type": "reasoning.delta", "text": self._combined_reasoning_text()})

    async def _handle_reasoning_summary_delta(self, params: dict[str, Any]) -> None:
        msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
        item_id = str(params.get("itemId") or msg.get("item_id") or msg.get("itemId") or "")
        summary_index = int(params.get("summaryIndex") or msg.get("summary_index") or msg.get("summaryIndex") or 0)
        reasoning = self._reasoning_state(item_id)
        reasoning.append_summary(summary_index, str(params.get("delta") or msg.get("delta") or ""))
        await self._emit_progress({"type": "reasoning.delta", "text": self._combined_reasoning_text()})

    async def _handle_command_output_delta(self, params: dict[str, Any]) -> None:
        msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
        item_id = str(params.get("itemId") or msg.get("item_id") or msg.get("itemId") or "")
        delta = str(params.get("delta") or msg.get("delta") or "")
        self.command_output_by_id[item_id] = f"{self.command_output_by_id.get(item_id, '')}{delta}"

    async def _handle_item_started(self, params: dict[str, Any]) -> None:
        item = self._extract_event_item(params)
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
            return
        if item_type == "fileChange":
            await self._emit_progress({"type": "file_change.started", "file_change": self._extract_file_change(item)})
            return
        if item_type == "collabAgentToolCall":
            await self._emit_progress({"type": "collab.started", "collab": self._extract_collab_tool_call(item)})

    async def _handle_item_completed(self, params: dict[str, Any]) -> None:
        item = self._extract_event_item(params)
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
        if item_type == "fileChange":
            await self._emit_progress({"type": "file_change.completed", "file_change": self._extract_file_change(item)})
            return
        if item_type == "collabAgentToolCall":
            await self._emit_progress({"type": "collab.completed", "collab": self._extract_collab_tool_call(item)})
            return
        if item_type == "plan":
            item_id = str(item.get("id") or "")
            text = str(item.get("text") or self.plan_text_by_id.get(item_id, "")).strip()
            if text:
                self.plan_text_by_id[item_id] = text
                await self._emit_progress({"type": "plan.completed", "text": text})

    async def _handle_token_usage_updated(self, params: dict[str, Any]) -> None:
        token_usage = params.get("tokenUsage") if isinstance(params.get("tokenUsage"), dict) else {}
        if not token_usage:
            msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
            info = msg.get("info") if isinstance(msg.get("info"), dict) else {}
            usage = info.get("last_token_usage") if isinstance(info.get("last_token_usage"), dict) else {}
            if not usage:
                usage = info.get("total_token_usage") if isinstance(info.get("total_token_usage"), dict) else {}
            if usage:
                self.usage = {
                    "input_tokens": usage.get("input_tokens"),
                    "cached_input_tokens": usage.get("cached_input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                    "reasoning_output_tokens": usage.get("reasoning_output_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                    "model_context_window": info.get("model_context_window"),
                }
                return
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
        if not turn:
            msg = params.get("msg") if isinstance(params.get("msg"), dict) else {}
            turn = {
                "status": msg.get("status") or "completed",
                "error": msg.get("error"),
            }
            last_agent_message = str(msg.get("last_agent_message") or msg.get("lastAgentMessage") or "").strip()
            if last_agent_message and not self.final_text:
                self.final_text = last_agent_message
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
        events = self.mapper.map_notification(method, params)
        self.turn_id = self.mapper.turn_id or self.turn_id
        for event in events:
            await self._apply_runtime_event(event)

    async def handle_server_request(
        self,
        client: "CodexAppServerClient",
        request_id: RequestId,
        method: str,
        params: dict[str, Any],
    ) -> bool:
        if self.done:
            return False
        requested = self.mapper.map_server_request(request_id, method, params)
        if requested is None:
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
            LOGGER.info(
                "codex ensure_thread resume candidate session_id=%s native_session_id=%s cwd=%s model=%s safety_mode=%s",
                session.session_id,
                thread_id,
                session.cwd,
                session.model_override or self.model,
                session.safety_mode,
            )
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
                    if context.on_thread_started is not None:
                        await context.on_thread_started(thread_id)
                    LOGGER.info(
                        "codex resumed existing thread session_id=%s thread_id=%s",
                        session.session_id,
                        thread_id,
                    )
                    return thread_id
            else:
                LOGGER.info(
                    "codex reusing in-memory thread session_id=%s thread_id=%s",
                    session.session_id,
                    thread_id,
                )
                return thread_id
        LOGGER.info(
            "codex starting fresh thread session_id=%s previous_native_session_id=%s cwd=%s model=%s safety_mode=%s",
            session.session_id,
            session.native_session_id,
            session.cwd,
            session.model_override or self.model,
            session.safety_mode,
        )
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
        if context.on_thread_started is not None:
            await context.on_thread_started(thread_id)
        LOGGER.info(
            "codex started fresh thread session_id=%s thread_id=%s",
            session.session_id,
            thread_id,
        )
        if context.on_progress is not None:
            await context.on_progress({"type": "thread.started", "threadId": thread_id})
        return thread_id

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

    async def list_threads(self, session: SessionRecord, context: BackendContext, limit: int = 20) -> tuple[list[CodexThreadSummary], str]:
        client = self._get_client(session, context)
        return await client.list_threads(limit=limit)

    async def read_thread(
        self,
        session: SessionRecord,
        context: BackendContext,
        thread_id: str,
        *,
        include_turns: bool = True,
    ) -> CodexThreadDetails:
        client = self._get_client(session, context)
        return await client.read_thread(thread_id, include_turns=include_turns)

    async def compact_thread(self, session: SessionRecord, context: BackendContext, thread_id: str) -> dict[str, Any]:
        client = self._get_client(session, context)
        return await client.compact_thread(thread_id)

    @classmethod
    async def shutdown_all(cls) -> None:
        for client in list(cls._clients.values()):
            await client.shutdown()
        cls._clients.clear()
