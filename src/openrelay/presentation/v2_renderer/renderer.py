"""
Codex v2 渲染器。

设计参考官方 Codex TUI 的 ChatWidget（chatwidget.rs），
直接消费 ServerNotification / ServerRequest，不经中间事件抽象层。

核心概念（对齐官方 TUI）：
- active_cell: 当前正在运行的 cell，同一时刻最多一个。工具运行时为 ExecCell /
  McpToolCallCell，Agent 消息流式期间由 StreamController 持续产出
  AgentMessageCell 片段
- transcript_cells: 已推入历史的不可变 cell 列表，按时间线排列
- flush_active_cell(): 将 active_cell 标记为 completed，推入 transcript_cells
- StreamController: 从 AgentMessageDelta 增量累积 markdown 文本，在换行边界
  产出 AgentMessageCell 片段推入 history，completed 后 consolidate 为单个
  AgentMarkdownCell（保留原始 markdown 源，支持飞书卡片 reflow）
- add_to_history(): 直接将一个 cell 推入 transcript_cells（用于 Warning、
  Error 等天生不可变的普通消息）
"""

from __future__ import annotations

import logging

from openrelay.backends.codex_adapter_v2.notifications import (
    AgentMessageDeltaNotification,
    ItemCompletedNotification,
    ServerNotification,
    TurnCompletedNotification,
    TurnStartedNotification,
)
from openrelay.backends.codex_adapter_v2.requests import ServerRequest

from .cells import (
    CollabAgentCell,
    ErrorCell,
    ExecCell,
    HookCell,
    McpToolCallCell,
    PatchHistoryCell,
    PlanStepItem,
    PlanUpdateCell,
    ReasoningCell,
    TerminalInteraction,
    WarningCell,
    WebSearchCell,
)
from .state import TurnV2State

LOGGER = logging.getLogger("openrelay.presentation.v2_renderer")


class TurnV2Renderer:
    """Codex v2 轮次渲染器，对应官方 ChatWidget。"""

    def __init__(self) -> None:
        self.state = TurnV2State()

    # ========================================================================
    # 主分发
    # ========================================================================

    def handle_server_notification(self, notification: ServerNotification) -> None:
        """ServerNotification 主分发入口。

        对应官方 chatwidget.rs:6218 handle_server_notification()。
        按 notification.variant 分发到对应的 on_* 方法。
        """
        variant = notification.variant
        method_name = f"_handle_{_camel_to_snake(variant)}"
        handler = getattr(self, method_name, None)
        if handler is not None:
            LOGGER.debug("v2 notification variant=%s method=%s", variant, notification.method)
            handler(notification)
        # 未知 variant 静默忽略（对齐官方 ignored 分支）

    def handle_server_request(self, request: ServerRequest) -> None:
        """ServerRequest — 入站审批请求，推入 transcript_cells，等待用户交互。"""
        # 审批 cell 暂不实现，待后续处理
        pass

    # ========================================================================
    # Turn 生命周期事件
    # ========================================================================

    def _handle_turn_started(self, notification: ServerNotification) -> None:
        params = notification.params
        turn_id = ""
        if isinstance(params, TurnStartedNotification):
            turn_id = str(params.turn.get("id") or "")
        elif isinstance(params, dict):
            turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
            turn_id = str(turn.get("id") or "")

        thread_id = ""
        if isinstance(params, TurnStartedNotification):
            thread_id = params.thread_id
        elif isinstance(params, dict):
            thread_id = str(params.get("threadId") or "")

        self.state.reset_for_new_turn(thread_id, turn_id)

    def _handle_turn_completed(self, notification: ServerNotification) -> None:
        if isinstance(notification.params, TurnCompletedNotification):
            turn = notification.params.turn
        elif isinstance(notification.params, dict):
            turn = notification.params.get("turn") if isinstance(notification.params.get("turn"), dict) else {}
        else:
            return

        # debug: log transcript state
        cell_types = [type(c).__name__ for c in self.state.transcript_cells]
        LOGGER.info(
            "turn_completed status=%s transcript_count=%d cell_types=%s",
            str(turn.get("status") or ""),
            len(cell_types),
            cell_types[-20:],  # last 20
        )

        raw_status = str(turn.get("status") or "")
        if raw_status == "completed":
            self.state.finalize_turn()
        elif raw_status == "interrupted":
            error = turn.get("error") if isinstance(turn.get("error"), dict) else {}
            msg = str(error.get("message") or "interrupted")
            self.state.finalize_with_error(f"Turn interrupted: {msg}")
        else:
            error = turn.get("error") if isinstance(turn.get("error"), dict) else {}
            msg = str(error.get("message") or f"Turn {raw_status or 'failed'}")
            self.state.finalize_with_error(msg)

    def _handle_error(self, notification: ServerNotification) -> None:
        if not isinstance(notification.params, dict):
            return
        will_retry = notification.params.get("willRetry")
        if will_retry:
            error = notification.params.get("error") if isinstance(notification.params.get("error"), dict) else {}
            self.state.status_header = str(error.get("message") or "retrying...")
            return

        error = notification.params.get("error") if isinstance(notification.params.get("error"), dict) else {}
        msg = str(error.get("message") or str(notification.params))
        self.state.finalize_with_error(msg)

    def _handle_warning(self, notification: ServerNotification) -> None:
        if not isinstance(notification.params, dict):
            return
        msg = str(notification.params.get("message") or "")
        if not msg or not self.state.should_display_warning(msg):
            return
        self.state.add_to_history(WarningCell(message=msg))

    def _handle_guardian_warning(self, notification: ServerNotification) -> None:
        if not isinstance(notification.params, dict):
            return
        msg = str(notification.params.get("message") or "")
        if not msg or not self.state.should_display_warning(msg):
            return
        self.state.add_to_history(WarningCell(message=f"[Guardian] {msg}"))

    # ========================================================================
    # 文本流事件
    # ========================================================================

    def _handle_agent_message_delta(self, notification: ServerNotification) -> None:
        if isinstance(notification.params, AgentMessageDeltaNotification):
            delta = notification.params.delta
        elif isinstance(notification.params, dict):
            delta = str(notification.params.get("delta") or "")
        else:
            return
        cells = self.state.stream_controller.push(delta)
        if cells:
            LOGGER.info("v2 cell ← %d AgentMessageCell(s)", len(cells))
        for cell in cells:
            self.state.add_to_history(cell)
        if self.state.status_header == "":
            self.state.status_header = "Working"

    def _handle_reasoning_text_delta(self, notification: ServerNotification) -> None:
        # 对齐官方：默认忽略 raw reasoning
        pass

    def _handle_reasoning_summary_text_delta(self, notification: ServerNotification) -> None:
        if not isinstance(notification.params, dict):
            return
        delta = str(notification.params.get("delta") or "")
        self.state.reasoning_buffer += delta

    def _handle_reasoning_summary_part_added(self, notification: ServerNotification) -> None:
        self.state.reasoning_buffer += "\n\n"

    def _handle_plan_delta(self, notification: ServerNotification) -> None:
        if not isinstance(notification.params, dict):
            return
        delta = str(notification.params.get("delta") or "")
        self.state.plan_stream_controller.push(delta)

    # ========================================================================
    # Item 生命周期事件
    # ========================================================================

    def _handle_item_started(self, notification: ServerNotification) -> None:
        if isinstance(notification.params, dict):
            item = _normalize_item(notification.params.get("item"))
        else:
            return

        item_type = str(item.get("type") or "")
        item_id = str(item.get("id") or "")
        LOGGER.info("v2 cell ← ItemStarted type=%-25s id=%s", item_type, item_id)

        if item_type == "commandExecution":
            self.state.flush_active_cell()
            exploration = _is_exploration_command(str(item.get("command") or ""))
            self.state.active_cell = ExecCell(
                call_id=item_id,
                command=str(item.get("command") or ""),
                exploration=exploration,
            )
        elif item_type == "mcpToolCall":
            self.state.flush_active_cell()
            self.state.active_cell = McpToolCallCell(
                call_id=item_id,
                server=str(item.get("server") or ""),
                tool=str(item.get("tool") or ""),
            )
        elif item_type == "fileChange":
            changes = item.get("changes") if isinstance(item.get("changes"), list) else []
            self.state.add_to_history(PatchHistoryCell(item_id=item_id, changes=changes))
        elif item_type == "webSearch":
            query = str(item.get("query") or "")
            self.state.add_to_history(WebSearchCell(item_id=item_id, query=query))
        elif item_type == "collabAgentToolCall":
            targets = list(item.get("receiverThreadIds") or []) if isinstance(item.get("receiverThreadIds"), list) else []
            self.state.add_to_history(
                CollabAgentCell(
                    item_id=item_id,
                    tool=str(item.get("tool") or ""),
                    prompt=str(item.get("prompt") or ""),
                    targets=targets,
                )
            )
        # agentMessage / reasoning / plan / userMessage → 不处理

    def _handle_item_completed(self, notification: ServerNotification) -> None:
        if isinstance(notification.params, ItemCompletedNotification):
            item = _normalize_item(notification.params.item)
        elif isinstance(notification.params, dict):
            item = _normalize_item(notification.params.get("item"))
        else:
            return

        item_type = str(item.get("type") or "")
        item_id = str(item.get("id") or "")
        LOGGER.info("v2 cell ← ItemCompleted type=%-25s id=%s", item_type, item_id)

        if item_type == "commandExecution":
            if isinstance(self.state.active_cell, ExecCell) and self.state.active_cell.call_id == item_id:
                self.state.active_cell.status = "completed"
                output = str(item.get("aggregatedOutput") or item.get("output_preview") or "")
                if output:
                    self.state.active_cell.output = output
                self.state.active_cell.exit_code = item.get("exitCode") if isinstance(item.get("exitCode"), int) else None
                self.state.flush_active_cell()

        elif item_type == "mcpToolCall":
            if isinstance(self.state.active_cell, McpToolCallCell) and self.state.active_cell.call_id == item_id:
                self.state.active_cell.status = "completed"
                self.state.flush_active_cell()

        elif item_type == "agentMessage":
            text = str(item.get("text") or "").strip()
            if text:
                phase = str(item.get("phase") or "").strip()
                if phase == "commentary":
                    pass  # commentary 暂不特殊处理
                else:
                    _ = text  # 最终文本由 consolidate 处理

        elif item_type == "reasoning":
            summary = item.get("summary")
            content = item.get("content")
            text_parts: list[str] = []
            if isinstance(summary, list):
                text_parts.extend(str(p) for p in summary)
            if isinstance(content, list):
                text_parts.extend(str(p) for p in content)
            text = "\n\n".join(p.strip() for p in text_parts if p.strip())
            if text:
                self.state.reasoning_buffer = text

        elif item_type == "fileChange":
            output = str(item.get("aggregatedOutput") or "")
            # 更新已有 PatchHistoryCell
            for cell in reversed(self.state.transcript_cells):
                if isinstance(cell, PatchHistoryCell) and cell.item_id == item_id:
                    cell.status = "completed"
                    if output:
                        cell.output = output
                    if self.state.latest_diff:
                        cell.diff = self.state.latest_diff
                    break

        elif item_type == "webSearch":
            for cell in reversed(self.state.transcript_cells):
                if isinstance(cell, WebSearchCell) and cell.item_id == item_id:
                    cell.status = "completed"
                    break

        elif item_type == "collabAgentToolCall":
            for cell in reversed(self.state.transcript_cells):
                if isinstance(cell, CollabAgentCell) and cell.item_id == item_id:
                    cell.status = "completed"
                    break

        # plan / userMessage → 不处理

    # ========================================================================
    # 工具输出增量事件
    # ========================================================================

    def _handle_command_execution_output_delta(self, notification: ServerNotification) -> None:
        if not isinstance(notification.params, dict):
            return
        item_id = str(notification.params.get("itemId") or "")
        delta = str(notification.params.get("delta") or "")
        if isinstance(self.state.active_cell, ExecCell) and self.state.active_cell.call_id == item_id:
            self.state.active_cell.output += delta

    def _handle_file_change_output_delta(self, notification: ServerNotification) -> None:
        if not isinstance(notification.params, dict):
            return
        item_id = str(notification.params.get("itemId") or "")
        delta = str(notification.params.get("delta") or "")
        for cell in reversed(self.state.transcript_cells):
            if isinstance(cell, PatchHistoryCell) and cell.item_id == item_id:
                cell.output += delta
                break

    def _handle_terminal_interaction(self, notification: ServerNotification) -> None:
        if not isinstance(notification.params, dict):
            return
        item_id = str(notification.params.get("itemId") or "")
        process_id = str(notification.params.get("processId") or "")
        stdin = str(notification.params.get("stdin") or "")
        if isinstance(self.state.active_cell, ExecCell) and self.state.active_cell.call_id == item_id:
            self.state.active_cell.terminal_interactions.append(
                TerminalInteraction(process_id=process_id, stdin=stdin)
            )

    # ========================================================================
    # Plan 事件
    # ========================================================================

    def _handle_turn_plan_updated(self, notification: ServerNotification) -> None:
        if not isinstance(notification.params, dict):
            return
        raw_steps = notification.params.get("plan") if isinstance(notification.params.get("plan"), list) else []
        steps: list[PlanStepItem] = []
        for raw in raw_steps:
            if not isinstance(raw, dict):
                continue
            step_text = str(raw.get("step") or raw.get("title") or "").strip()
            if not step_text:
                continue
            raw_status = str(raw.get("status") or "pending")
            norm_status = raw_status
            if norm_status == "inProgress":
                norm_status = "in_progress"
            if norm_status not in ("pending", "in_progress", "completed"):
                norm_status = "pending"
            steps.append(PlanStepItem(step=step_text, status=norm_status))  # type: ignore[arg-type]
        explanation = str(notification.params.get("explanation") or "")
        self.state.add_to_history(PlanUpdateCell(steps=steps, explanation=explanation))

    # ========================================================================
    # Diff 事件
    # ========================================================================

    def _handle_turn_diff_updated(self, notification: ServerNotification) -> None:
        if not isinstance(notification.params, dict):
            return
        self.state.latest_diff = str(notification.params.get("diff") or "")

    # ========================================================================
    # Hook 事件
    # ========================================================================

    def _handle_hook_started(self, notification: ServerNotification) -> None:
        hook_type = _hook_type_from_params(notification.params)
        self.state.active_hook_cell = HookCell(hook_type=hook_type)

    def _handle_hook_completed(self, notification: ServerNotification) -> None:
        if self.state.active_hook_cell is not None:
            self.state.active_hook_cell.status = "completed"
            self.state.add_to_history(self.state.active_hook_cell)
            self.state.active_hook_cell = None

    # ========================================================================
    # 以下 variant 在官方 TUI 中忽略，v2 同样忽略（不设 handler）：
    #   ThreadStarted, ThreadStatusChanged, ThreadArchived, ThreadUnarchived,
    #   ThreadClosed, SkillsChanged, ThreadNameUpdated, ThreadGoalUpdated,
    #   ThreadGoalCleared, ThreadTokenUsageUpdated, RawResponseItemCompleted,
    #   CommandExecOutputDelta, ProcessOutputDelta, ProcessExited,
    #   FileChangePatchUpdated, McpToolCallProgress,
    #   ServerRequestResolved, McpServerOauthLoginCompleted,
    #   McpServerStatusUpdated, AccountUpdated, AccountRateLimitsUpdated,
    #   AppListUpdated, RemoteControlStatusChanged,
    #   ExternalAgentConfigImportCompleted, FsChanged,
    #   ContextCompacted, ModelRerouted, ModelVerification,
    #   DeprecationNotice, ConfigWarning,
    #   FuzzyFileSearchSessionUpdated, FuzzyFileSearchSessionCompleted,
    #   所有 thread/realtime/*, WindowsWorldWritableWarning,
    #   WindowsSandboxSetupCompleted, AccountLoginCompleted,
    #   ReasoningSummaryPartAdded (处理为 segmentation marker),
    #   PlanDelta (由 PlanStreamController 处理)
    # ========================================================================

    # ---- 卡牌输出入口 ----

    def build_streaming_content(self) -> str:
        from .card_builder import render_transcript
        return render_transcript(self.state)

    def build_streaming_card_json(self) -> dict:
        from .card_builder import build_streaming_card_json
        return build_streaming_card_json(self.state)

    def build_initial_card_json(self) -> dict:
        from .card_builder import build_initial_card_json
        return build_initial_card_json()

    def build_final_card_json(self, *, fallback_text: str = "") -> dict:
        from .card_builder import build_final_card_json
        return build_final_card_json(self.state, fallback_text=fallback_text)

    def bump_spinner(self) -> None:
        self.state.spinner_frame = (self.state.spinner_frame + 1) % 3


# ============================================================================
# helpers
# ============================================================================


def _camel_to_snake(name: str) -> str:
    """TurnStarted → turn_started, AgentMessageDelta → agent_message_delta."""
    result: list[str] = []
    for char in name:
        if char.isupper() and result:
            result.append("_")
        result.append(char.lower())
    return "".join(result)


def _normalize_item(item: object) -> dict:
    if not isinstance(item, dict):
        return {}
    normalized = dict(item)
    typ = str(item.get("type") or "").strip()
    if typ:
        normalized["type"] = typ[:1].lower() + typ[1:]
    return normalized


def _is_exploration_command(command: str) -> bool:
    normalized = " ".join(command.split()).strip().lower()
    for prefix in ("rg", "grep", "cat", "sed", "find", "fd", "ls", "tree", "pwd",
                    "git status", "git diff", "git show", "git log"):
        if normalized == prefix or normalized.startswith(f"{prefix} "):
            return True
    return False


def _hook_type_from_params(params: object) -> str:
    if isinstance(params, dict):
        run = params.get("run") if isinstance(params.get("run"), dict) else {}
        return str(run.get("type") or run.get("name") or "hook")
    return "hook"
