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
                CodexEventDescriptor("turn/started", "v2", "turn.started", "system", "v2-only", "turn.started"),
                CodexEventDescriptor("item/agentMessage/delta", "v2", "assistant.delta", "render", "v2-only", "assistant.delta", "item-delta"),
                CodexEventDescriptor("item/reasoning/textDelta", "v2", "reasoning.delta", "render", "v2-only", "reasoning.delta", "reasoning-content"),
                CodexEventDescriptor("item/reasoning/summaryTextDelta", "v2", "reasoning.delta", "render", "v2-only", "reasoning.delta", "reasoning-summary"),
                CodexEventDescriptor("item/reasoning/summaryPartAdded", "v2", "reasoning.summary-part-added", "ignore", "v2-only"),
                CodexEventDescriptor("item/plan/delta", "v2", "plan.delta", "render", "v2-only", "plan.delta"),
                CodexEventDescriptor("turn/plan/updated", "v2", "plan.updated", "render", "v2-only", "plan.updated", "plan"),
                CodexEventDescriptor("item/commandExecution/outputDelta", "v2", "tool.progress", "render", "v2-only", "tool.progress", "tool-output"),
                CodexEventDescriptor("item/fileChange/outputDelta", "v2", "tool.progress", "render", "v2-only", "tool.progress", "tool-output"),
                CodexEventDescriptor("item/commandExecution/terminalInteraction", "v2", "terminal.interaction", "observe", "v2-only", "observe"),
                CodexEventDescriptor("item/mcpToolCall/progress", "v2", "tool.progress", "render", "v2-only", "tool.progress", "tool-output"),
                CodexEventDescriptor("serverRequest/resolved", "v2", "approval.resolved", "system", "v2-only", "approval.resolved", "approval"),
                CodexEventDescriptor("item/started", "v2", "item.started", "render", "v2-only", "item.started"),
                CodexEventDescriptor("item/completed", "v2", "item.completed", "render", "v2-only", "item.completed"),
                CodexEventDescriptor("thread/tokenUsage/updated", "v2", "usage.updated", "render", "v2-only", "usage.updated", "usage"),
                CodexEventDescriptor("turn/completed", "v2", "turn.terminal", "system", "v2-only", "turn.terminal", "terminal", "terminal"),
                CodexEventDescriptor("error", "v2", "turn.error", "system", "v2-only", "turn.error", "terminal", "terminal"),
                CodexEventDescriptor("account/rateLimits/updated", "v2", "account.rate_limits.updated", "system", "v2-only"),
                CodexEventDescriptor("thread/status/changed", "v2", "thread.status.changed", "system", "v2-only"),
                CodexEventDescriptor("skills/changed", "v2", "skills.changed", "system", "v2-only"),
                CodexEventDescriptor("turn/diff/updated", "v2", "thread.diff.updated", "system", "v2-only"),
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
