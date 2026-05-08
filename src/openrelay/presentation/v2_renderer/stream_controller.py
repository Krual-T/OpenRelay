"""
流式控制器。

对齐官方 Codex TUI streaming/controller.rs：
- StreamController: AgentMessageDelta → AgentMessageCell 片段
- PlanStreamController: PlanDelta → ProposedPlanCell

飞书场景简化：不需要 adaptive chunking（终端逐行动画），
所有行直接 push 到 history，覆盖式更新卡片内容。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .cells import AgentMessageCell, ProposedPlanCell


@dataclass(slots=True)
class StreamController:
    """Agent 消息流控制器。

    从 AgentMessageDelta 增量累积 markdown 源文本，
    在换行边界产出 AgentMessageCell 片段。
    """

    raw_source: str = ""
    emitted_len: int = 0  # 已 emit 的 raw_source 长度
    is_first: bool = True

    def push(self, delta: str) -> list[AgentMessageCell]:
        """推入 delta 增量，返回新产出的 AgentMessageCell 片段列表。"""
        if not delta:
            return []
        self.raw_source += delta
        return self._emit_complete_lines()

    def flush_partial(self) -> list[AgentMessageCell]:
        """强制 flush 当前未完成的行（即时有换行才完整）。"""
        cells = self._emit_complete_lines()
        # 如果还有未 emit 的内容（不完整行），也一起 emit
        pending = self.raw_source[self.emitted_len :].strip()
        if pending:
            cells.append(AgentMessageCell(source_line=pending, is_first=self.is_first))
            self.is_first = False
            self.emitted_len = len(self.raw_source)
        return cells

    def _emit_complete_lines(self) -> list[AgentMessageCell]:
        """Emit 完整的行（以换行符结尾的）。"""
        pending = self.raw_source[self.emitted_len :]
        lines = pending.split("\n")
        complete_lines = lines[:-1] if len(lines) > 1 else []

        cells: list[AgentMessageCell] = []
        for line in complete_lines:
            stripped = line.strip()
            if stripped:
                cells.append(AgentMessageCell(source_line=stripped, is_first=self.is_first))
                self.is_first = False
            self.emitted_len += len(line) + 1  # +1 for the \n

        return cells

    def finalize(self) -> tuple[list[AgentMessageCell], str]:
        """结束流，返回剩余行 + 完整 raw_source。"""
        remaining = self.raw_source[self.emitted_len :].strip()
        cells: list[AgentMessageCell] = []
        if remaining:
            cells.append(AgentMessageCell(source_line=remaining, is_first=self.is_first))
        raw = self.raw_source.strip()
        self._reset()
        return cells, raw

    def _reset(self) -> None:
        self.raw_source = ""
        self.emitted_len = 0
        self.is_first = True


@dataclass(slots=True)
class PlanStreamController:
    """计划流控制器。

    从 PlanDelta 增量累积 plan markdown 源文本，
    finalize 时产出 ProposedPlanCell。
    """

    raw_source: str = ""

    def push(self, delta: str) -> None:
        self.raw_source += delta

    def finalize(self) -> ProposedPlanCell | None:
        source = self.raw_source.strip()
        self.raw_source = ""
        if not source:
            return None
        return ProposedPlanCell(source=source)
