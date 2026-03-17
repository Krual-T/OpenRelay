from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


EventPolicy = Literal["render", "system", "ignore", "observe"]
EventRoute = Literal["v1", "v2"]
SupportLevel = Literal["v1-only", "v2-only", "dual"]


class CodexConsumptionMode(StrEnum):
    HYBRID = "hybrid"
    TYPED_ONLY = "typed-only"


@dataclass(frozen=True, slots=True)
class CodexEventDescriptor:
    method: str
    route: EventRoute
    semantic_name: str
    policy: EventPolicy
    support_level: SupportLevel
    projector: str = ""
    dedupe_scope: str = ""
    terminal_kind: str = ""


class CodexEventRegistry:
    def __init__(self) -> None:
        self._descriptors = {
            descriptor.method: descriptor
            for descriptor in (
                CodexEventDescriptor("thread/started", "v2", "session.started", "system", "v2-only", "session.started"),
                CodexEventDescriptor("turn/started", "v2", "turn.started", "system", "dual", "turn.started"),
                CodexEventDescriptor("codex/event/task_started", "v1", "turn.started", "system", "dual", "turn.started"),
                CodexEventDescriptor("item/agentMessage/delta", "v2", "assistant.delta", "render", "dual", "assistant.delta", "item-delta"),
                CodexEventDescriptor("codex/event/agent_message_content_delta", "v1", "assistant.delta", "render", "dual", "assistant.delta", "item-delta"),
                CodexEventDescriptor("codex/event/agent_message_delta", "v1", "assistant.delta", "render", "dual", "assistant.delta", "item-delta"),
                CodexEventDescriptor("item/reasoning/textDelta", "v2", "reasoning.delta", "render", "dual", "reasoning.delta", "reasoning-content"),
                CodexEventDescriptor("codex/event/reasoning_content_delta", "v1", "reasoning.delta", "render", "dual", "reasoning.delta", "reasoning-content"),
                CodexEventDescriptor("item/reasoning/summaryTextDelta", "v2", "reasoning.delta", "render", "dual", "reasoning.delta", "reasoning-summary"),
                CodexEventDescriptor("codex/event/reasoning_summary_text_delta", "v1", "reasoning.delta", "render", "dual", "reasoning.delta", "reasoning-summary"),
                CodexEventDescriptor("item/reasoning/summaryPartAdded", "v2", "reasoning.summary-part-added", "ignore", "v2-only"),
                CodexEventDescriptor("item/plan/delta", "v2", "plan.delta", "render", "v2-only", "plan.delta"),
                CodexEventDescriptor("turn/plan/updated", "v2", "plan.updated", "render", "dual", "plan.updated", "plan"),
                CodexEventDescriptor("codex/event/plan_update", "v1", "plan.updated", "render", "v1-only", "plan.updated", "plan"),
                CodexEventDescriptor("item/commandExecution/outputDelta", "v2", "tool.progress", "render", "dual", "tool.progress", "tool-output"),
                CodexEventDescriptor("codex/event/command_output_delta", "v1", "tool.progress", "render", "dual", "tool.progress", "tool-output"),
                CodexEventDescriptor("codex/event/exec_command_output_delta", "v1", "tool.progress", "render", "v1-only", "tool.progress", "tool-output"),
                CodexEventDescriptor("item/fileChange/outputDelta", "v2", "tool.progress", "render", "v2-only", "tool.progress", "tool-output"),
                CodexEventDescriptor("item/commandExecution/terminalInteraction", "v2", "terminal.interaction", "observe", "dual", "observe"),
                CodexEventDescriptor("codex/event/terminal_interaction", "v1", "terminal.interaction", "observe", "v1-only", "observe"),
                CodexEventDescriptor("item/mcpToolCall/progress", "v2", "tool.progress", "render", "v2-only", "tool.progress", "tool-output"),
                CodexEventDescriptor("serverRequest/resolved", "v2", "approval.resolved", "system", "v2-only", "approval.resolved", "approval"),
                CodexEventDescriptor("item/started", "v2", "item.started", "render", "dual", "item.started"),
                CodexEventDescriptor("codex/event/item_started", "v1", "item.started", "render", "dual", "item.started"),
                CodexEventDescriptor("item/completed", "v2", "item.completed", "render", "dual", "item.completed"),
                CodexEventDescriptor("codex/event/item_completed", "v1", "item.completed", "render", "dual", "item.completed"),
                CodexEventDescriptor("thread/tokenUsage/updated", "v2", "usage.updated", "render", "dual", "usage.updated", "usage"),
                CodexEventDescriptor("codex/event/token_count", "v1", "usage.updated", "render", "dual", "usage.updated", "usage"),
                CodexEventDescriptor("turn/completed", "v2", "turn.terminal", "system", "dual", "turn.terminal", "terminal", "terminal"),
                CodexEventDescriptor("codex/event/task_complete", "v1", "turn.terminal", "system", "dual", "turn.terminal", "terminal", "terminal"),
                CodexEventDescriptor("codex/event/turn_aborted", "v1", "turn.terminal", "system", "v1-only", "turn.terminal", "terminal", "terminal"),
                CodexEventDescriptor("error", "v2", "turn.error", "system", "v2-only", "turn.error", "terminal", "terminal"),
                CodexEventDescriptor("account/rateLimits/updated", "v2", "account.rate_limits.updated", "system", "v2-only"),
                CodexEventDescriptor("thread/status/changed", "v2", "thread.status.changed", "system", "v2-only"),
                CodexEventDescriptor("skills/changed", "v2", "skills.changed", "system", "v2-only"),
                CodexEventDescriptor("turn/diff/updated", "v2", "thread.diff.updated", "system", "v2-only"),
                CodexEventDescriptor("codex/event/agent_reasoning", "v1", "reasoning.delta", "observe", "v1-only", "observe"),
                CodexEventDescriptor("codex/event/agent_reasoning_section_break", "v1", "reasoning.section.break", "ignore", "v1-only"),
                CodexEventDescriptor("codex/event/raw_response_item", "v1", "raw.response.item", "ignore", "v1-only"),
                CodexEventDescriptor("codex/event/user_message", "v1", "user.message.echo", "ignore", "v1-only"),
                CodexEventDescriptor("codex/event/task_started", "v1", "task.started.legacy", "ignore", "v1-only"),
                CodexEventDescriptor("codex/event/skills_update_available", "v1", "skills.update.available", "ignore", "v1-only"),
                CodexEventDescriptor("codex/event/mcp_startup_complete", "v1", "mcp.startup.complete", "ignore", "v1-only"),
            )
        }

    def lookup(self, method: str, mode: CodexConsumptionMode) -> CodexEventDescriptor | None:
        descriptor = self._descriptors.get(method)
        if descriptor is None:
            return None
        if not self.is_enabled(descriptor, mode):
            return None
        return descriptor

    def is_enabled(self, descriptor: CodexEventDescriptor, mode: CodexConsumptionMode) -> bool:
        if mode == CodexConsumptionMode.HYBRID:
            return True
        return descriptor.route == "v2"

