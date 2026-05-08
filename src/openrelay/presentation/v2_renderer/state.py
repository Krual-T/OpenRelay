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

        # consolidate AgentMessageCell 只在每组连续末尾 → AgentMarkdownCell
        # 这样中间被工具隔开的 Agent 文本保持原位，只有最后一段变 MarkdownCell
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
        """合并 transcript 末尾连续的一组 AgentMessageCell → AgentMarkdownCell。

        对齐官方 TUI trailing_run_start + ConsolidateAgentMessage：
        只合并最末尾连续的一段，不碰中间被其他 cell 隔开的。
        """
        # 从末尾往前找最后一个 AgentMessageCell 的连续段
        end = len(self.transcript_cells)
        start = end
        for i in range(end - 1, -1, -1):
            if isinstance(self.transcript_cells[i], AgentMessageCell):
                start = i
            else:
                break

        if start >= end:
            return

        group = self.transcript_cells[start:end]
        source = "\n".join(c.source_line for c in group)  # type: ignore[attr-defined]
        consolidated = AgentMarkdownCell(source=source)

        # splice: 替换 start..end 为一个 AgentMarkdownCell
        self.transcript_cells[start:end] = [consolidated]

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
