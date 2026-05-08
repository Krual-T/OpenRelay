"""
TurnV2State — 渲染器内部状态。

对应官方 ChatWidget 的实例字段，管理：
- active_cell（当前运行中的 cell）
- transcript_cells（不可变历史）
- stream controller（AgentMessageDelta → AgentMessageCell）
- 各种 buffer（reasoning、plan_delta、latest_diff）
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .cells import (
    AgentMarkdownCell,
    AgentMessageCell,
    Cell,
    ErrorCell,
    ExecCell,
    FinalSeparatorCell,
    HookCell,
    McpToolCallCell,
)
from .stream_controller import PlanStreamController, StreamController


@dataclass(slots=True)
class TurnV2State:
    """轮次渲染状态。

    所有 mutation 都通过方法完成，不直接修改字段。
    """

    thread_id: str = ""
    turn_id: str = ""
    agent_turn_running: bool = False

    active_cell: ExecCell | McpToolCallCell | None = None
    active_hook_cell: HookCell | None = None

    transcript_cells: list[Cell] = field(default_factory=list)

    stream_controller: StreamController = field(default_factory=StreamController)
    plan_stream_controller: PlanStreamController = field(default_factory=PlanStreamController)

    reasoning_buffer: str = ""
    plan_delta_buffer: str = ""
    latest_diff: str = ""

    status_header: str = ""
    spinner_frame: int = 0
    turn_started_at: float = 0.0

    # 警告去重
    warning_display_state: set[str] = field(default_factory=set)

    # ---- cell 生命周期方法 ------------------------------------------------

    def flush_active_cell(self) -> None:
        """将 active_cell 标记为 completed，推入 transcript_cells。"""
        if self.active_cell is None:
            return
        self.active_cell.status = "completed"
        self.add_to_history(self.active_cell)
        self.active_cell = None

    def add_to_history(self, cell: Cell) -> None:
        """将 cell 推入 transcript_cells。"""
        self.transcript_cells.append(cell)

    def finalize_turn(self) -> None:
        """结束 turn：flush + finalize streams + consolidate + FinalSeparator。

        对齐官方 on_task_complete() + finalize_turn()。
        """
        self.flush_active_cell()

        # finalize stream controller — 先把剩余行推入 history
        remaining_cells, _raw_source = self.stream_controller.finalize()
        for cell in remaining_cells:
            self.add_to_history(cell)

        # consolidate AgentMessageCell 片段 → AgentMarkdownCell
        self.consolidate_agent_message()

        # finalize plan stream controller
        plan_cell = self.plan_stream_controller.finalize()
        if plan_cell is not None:
            self.add_to_history(plan_cell)

        # FinalSeparator
        elapsed = time.monotonic() - self.turn_started_at if self.turn_started_at > 0 else 0.0
        self.add_to_history(FinalSeparatorCell(elapsed_seconds=elapsed))

        self.agent_turn_running = False

    def consolidate_agent_message(self) -> None:
        """将 transcript_cells 中的连续 AgentMessageCell 合并为单个 AgentMarkdownCell。

        对齐官方 ConsolidateAgentMessage event 处理。
        """
        agent_cells: list[AgentMessageCell] = []
        indices: list[int] = []
        for i, cell in enumerate(self.transcript_cells):
            if isinstance(cell, AgentMessageCell):
                agent_cells.append(cell)
                indices.append(i)

        if len(agent_cells) <= 1:
            return

        # 合并所有 AgentMessageCell 的 source_line
        source = "\n".join(c.source_line for c in agent_cells)

        # 从后往前替换，避免索引偏移
        for i in reversed(indices):
            self.transcript_cells.pop(i)

        self.transcript_cells.insert(indices[0], AgentMarkdownCell(source=source))

    def finalize_with_error(self, message: str) -> None:
        """错误结束 turn：flush active_cell 为 failed + ErrorCell + FinalSeparator。"""
        if self.active_cell is not None:
            self.active_cell.status = "failed"
            self.add_to_history(self.active_cell)
            self.active_cell = None

        self.add_to_history(ErrorCell(message=message))

        elapsed = time.monotonic() - self.turn_started_at if self.turn_started_at > 0 else 0.0
        self.add_to_history(FinalSeparatorCell(elapsed_seconds=elapsed))

        self.agent_turn_running = False

    # ---- warning 去重 -----------------------------------------------------

    def should_display_warning(self, message: str) -> bool:
        """检查警告消息是否应该展示（去重）。"""
        if message in self.warning_display_state:
            return False
        self.warning_display_state.add(message)
        return True

    @property
    def assistant_text(self) -> str:
        """从 transcript_cells 提取最终 assistant 文本。"""
        for cell in reversed(self.transcript_cells):
            from .cells import AgentMarkdownCell
            if isinstance(cell, AgentMarkdownCell):
                return cell.source.strip()
        return ""

    # ---- reset -----------------------------------------------------------

    def reset_for_new_turn(self, thread_id: str, turn_id: str) -> None:
        """重置所有 per-turn 状态，准备新一轮。"""
        self.flush_active_cell()
        self.thread_id = thread_id
        self.turn_id = turn_id
        self.agent_turn_running = True
        self.active_cell = None
        self.active_hook_cell = None
        self.stream_controller = StreamController()
        self.plan_stream_controller = PlanStreamController()
        self.reasoning_buffer = ""
        self.plan_delta_buffer = ""
        self.latest_diff = ""
        self.status_header = "Working"
        self.spinner_frame = 0
        self.turn_started_at = time.monotonic()
        self.warning_display_state.clear()
