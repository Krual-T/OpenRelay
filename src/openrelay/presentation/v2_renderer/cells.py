"""
Cell 数据模型。

对齐官方 Codex TUI 的 HistoryCell 体系。
每个 cell 是纯数据 dataclass，不含渲染逻辑（渲染逻辑在 cell_renderer.py）。

active_cell 类型：ExecCell | McpToolCallCell（只有这两类需要原地更新 output）。
其他 cell 类型创建后直接 push 到 transcript_cells，不可变。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

# 截断常量（对齐官方 TUI）
TOOL_OUTPUT_MAX_LINES: int = 5
USER_SHELL_MAX_LINES: int = 50

CellStatus = Literal["running", "completed", "failed"]


# ============================================================================
# 工具类 cell（可设为 active_cell）
# ============================================================================


@dataclass(slots=True)
class ExecCell:
    """命令执行 cell。对应官方 ExecCell。

    可为 active_cell — 运行时通过 CommandExecutionOutputDelta 追加 output，
    completed 时 flush 到 transcript_cells。
    """

    call_id: str
    command: str = ""
    output: str = ""
    exit_code: int | None = None
    status: CellStatus = "running"
    started_at: float = 0.0
    duration_ms: int = 0

    # 用于 exploration 模式（rg/grep/find 等只读命令）
    exploration: bool = False

    # terminal interaction 历史
    terminal_interactions: list[TerminalInteraction] = field(default_factory=list)


@dataclass(slots=True)
class TerminalInteraction:
    """终端交互记录（stdin 输入）。"""
    process_id: str = ""
    stdin: str = ""


@dataclass(slots=True)
class McpToolCallCell:
    """MCP 工具调用 cell。对应官方 McpToolCallCell。

    可为 active_cell — 运行时通过 McpToolCallProgress 追加 result，
    completed 时 flush 到 transcript_cells。
    """

    call_id: str
    server: str = ""
    tool: str = ""
    arguments: dict | None = None
    result: str = ""
    status: CellStatus = "running"
    duration_ms: int = 0


# ============================================================================
# 非 active 工具类 cell（创建后直接推入 history）
# ============================================================================


@dataclass(slots=True)
class PatchHistoryCell:
    """文件变更 cell。对应官方 PatchHistoryCell。"""

    item_id: str
    changes: list[dict] = field(default_factory=list)
    output: str = ""
    diff: str = ""
    status: CellStatus = "running"


@dataclass(slots=True)
class WebSearchCell:
    """Web 搜索 cell。对应官方 WebSearchCell。"""

    item_id: str
    query: str = ""
    action: str = ""
    status: CellStatus = "running"


@dataclass(slots=True)
class CollabAgentCell:
    """协作 agent 调用 cell。对应官方 CollabAgentToolCall 渲染。"""

    item_id: str
    tool: str = ""
    prompt: str = ""
    targets: list[str] = field(default_factory=list)
    status: CellStatus = "running"


# ============================================================================
# Agent 消息 cell
# ============================================================================


@dataclass(slots=True)
class AgentMessageCell:
    """Agent 消息流式片段。对应官方 AgentMessageCell。

    由 StreamController 在换行边界产出。
    is_first 标记该片段是否为本次 turn 的首行（控制 bullet 前缀）。
    """

    source_line: str
    is_first: bool = False


@dataclass(slots=True)
class AgentMarkdownCell:
    """Agent 消息合并 cell。对应官方 AgentMarkdownCell。

    turn completed 时由 consolidate_agent_message() 将多个
    AgentMessageCell 合并为一个，保留完整 markdown 源，
    支持飞书卡片 reflow。
    """

    source: str = ""


# ============================================================================
# 推理 cell
# ============================================================================


@dataclass(slots=True)
class ReasoningCell:
    """推理文本 cell。对应官方 ReasoningSummaryCell。

    从 ReasoningSummaryTextDelta 累积。
    """

    text: str = ""


# ============================================================================
# Hook cell
# ============================================================================


@dataclass(slots=True)
class HookCell:
    """钩子 cell。对应官方 HookCell。

    可为 active_hook_cell — 可与 active_cell 并存。
    """

    hook_type: str = ""
    status: CellStatus = "running"
    messages: list[str] = field(default_factory=list)


# ============================================================================
# Plan cell
# ============================================================================


@dataclass(slots=True)
class PlanStepItem:
    """单个计划步骤。"""
    step: str
    status: Literal["pending", "in_progress", "completed"] = "pending"


@dataclass(slots=True)
class PlanUpdateCell:
    """计划更新 cell。对应官方 PlanUpdateCell。

    由 TurnPlanUpdated 产出。
    """

    steps: list[PlanStepItem] = field(default_factory=list)
    explanation: str = ""


@dataclass(slots=True)
class ProposedPlanCell:
    """计划提案 cell。对应官方 ProposedPlanCell。

    由 PlanStreamController.finalize() 在 turn completed 时产出。
    """

    source: str = ""


# ============================================================================
# 通知类 cell（普通消息，不走 active_cell）
# ============================================================================


@dataclass(slots=True)
class SeparatorCell:
    """Agent 消息组之间的分割线 cell。流式卡片中的视觉分隔。

    丢弃规则：最终卡片中，紧邻最后一个 AgentMarkdownCell 之前的 SeparatorCell 被丢弃。
    """


@dataclass(slots=True)
class WarningCell:
    """警告 cell。对应官方 WarningEvent。

    直接 add_to_history()，不走 active_cell。
    """

    message: str = ""


@dataclass(slots=True)
class ErrorCell:
    """错误 cell。对应官方 ErrorEvent。

    直接 add_to_history()。
    """

    message: str = ""


# ============================================================================
# 分隔 cell
# ============================================================================


@dataclass(slots=True)
class FinalSeparatorCell:
    """Turn 完成分隔线。对应官方 FinalMessageSeparator。

    turn completed 时由 finalize_turn() 产出。
    展示 "Worked for Xs" + runtime metrics。
    """

    elapsed_seconds: float = 0.0
    metrics: str = ""


# ============================================================================
# Cell 联合类型
# ============================================================================

# 所有 cell 类型
Cell: TypeAlias = (
    ExecCell
    | McpToolCallCell
    | PatchHistoryCell
    | WebSearchCell
    | CollabAgentCell
    | AgentMessageCell
    | AgentMarkdownCell
    | ReasoningCell
    | HookCell
    | PlanUpdateCell
    | ProposedPlanCell
    | SeparatorCell
    | WarningCell
    | ErrorCell
    | FinalSeparatorCell
)

# 只有这两类可以是 active_cell（需要原地更新 output）
ActiveCell: TypeAlias = ExecCell | McpToolCallCell
