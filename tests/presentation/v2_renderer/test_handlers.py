"""测试 TurnV2Renderer handler 分发链路。"""

from openrelay.backends.codex_adapter_v2.notifications import (
    AgentMessageDeltaNotification,
    ItemCompletedNotification,
    ServerNotification,
    TurnCompletedNotification,
    TurnStartedNotification,
)
from openrelay.presentation.v2_renderer import TurnV2Renderer
from openrelay.presentation.v2_renderer.cells import (
    AgentMarkdownCell,
    AgentMessageCell,
    CollabAgentCell,
    ErrorCell,
    ExecCell,
    FinalSeparatorCell,
    McpToolCallCell,
    PatchHistoryCell,
    PlanUpdateCell,
    ReasoningCell,
    WarningCell,
    WebSearchCell,
)


class TestTurnLifecycle:
    def test_turn_started_resets_state(self):
        r = TurnV2Renderer()
        r.handle_server_notification(
            ServerNotification(
                variant="TurnStarted",
                method="turn/started",
                params=TurnStartedNotification(
                    thread_id="00000000-0000-0000-0000-000000000001",
                    turn={"id": "turn-1", "status": "inProgress"},
                ),
            )
        )
        assert r.state.agent_turn_running is True
        assert r.state.turn_id == "turn-1"
        assert r.state.status_header == "Working"
        assert r.state.transcript_cells == []

    def test_turn_completed_completed(self):
        r = TurnV2Renderer()
        r.state.agent_turn_running = True
        r.handle_server_notification(
            ServerNotification(
                variant="TurnCompleted",
                method="turn/completed",
                params=TurnCompletedNotification(
                    thread_id="", turn={"id": "turn-1", "status": "completed"}
                ),
            )
        )
        assert r.state.agent_turn_running is False
        assert any(isinstance(c, FinalSeparatorCell) for c in r.state.transcript_cells)

    def test_turn_completed_interrupted(self):
        r = TurnV2Renderer()
        r.state.agent_turn_running = True
        r.handle_server_notification(
            ServerNotification(
                variant="TurnCompleted",
                method="turn/completed",
                params=TurnCompletedNotification(
                    thread_id="", turn={"id": "turn-1", "status": "interrupted"}
                ),
            )
        )
        assert r.state.agent_turn_running is False
        assert any(isinstance(c, ErrorCell) and "interrupted" in c.message for c in r.state.transcript_cells)

    def test_turn_completed_failed(self):
        r = TurnV2Renderer()
        r.state.agent_turn_running = True
        r.handle_server_notification(
            ServerNotification(
                variant="TurnCompleted",
                method="turn/completed",
                params=TurnCompletedNotification(
                    thread_id="",
                    turn={"id": "turn-1", "status": "failed", "error": {"message": "boom"}},
                ),
            )
        )
        assert r.state.agent_turn_running is False
        assert any(isinstance(c, ErrorCell) for c in r.state.transcript_cells)

    def test_error_will_retry_updates_status_header(self):
        r = TurnV2Renderer()
        r.state.agent_turn_running = True
        r.handle_server_notification(
            ServerNotification(
                variant="Error",
                method="error",
                params={"error": {"message": "overloaded"}, "willRetry": True},
            )
        )
        assert r.state.agent_turn_running is True
        assert "overloaded" in r.state.status_header

    def test_error_no_retry_finalizes_turn(self):
        r = TurnV2Renderer()
        r.state.agent_turn_running = True
        r.handle_server_notification(
            ServerNotification(
                variant="Error",
                method="error",
                params={"error": {"message": "fatal"}, "willRetry": False},
            )
        )
        assert r.state.agent_turn_running is False
        assert any(isinstance(c, ErrorCell) for c in r.state.transcript_cells)

    def test_warning_deduplicates(self):
        r = TurnV2Renderer()
        r.handle_server_notification(
            ServerNotification(
                variant="Warning", method="warning", params={"message": "dup test"}
            )
        )
        assert len([c for c in r.state.transcript_cells if isinstance(c, WarningCell)]) == 1

        r.handle_server_notification(
            ServerNotification(
                variant="Warning", method="warning", params={"message": "dup test"}
            )
        )
        assert len([c for c in r.state.transcript_cells if isinstance(c, WarningCell)]) == 1  # deduped

    def test_warning_different_messages_both_shown(self):
        r = TurnV2Renderer()
        r.handle_server_notification(
            ServerNotification(variant="Warning", method="warning", params={"message": "msg1"})
        )
        r.handle_server_notification(
            ServerNotification(variant="Warning", method="warning", params={"message": "msg2"})
        )
        assert len([c for c in r.state.transcript_cells if isinstance(c, WarningCell)]) == 2


class TestTextStreaming:
    def test_agent_message_delta_creates_cells(self):
        r = TurnV2Renderer()
        r.handle_server_notification(
            ServerNotification(
                variant="AgentMessageDelta",
                method="item/agentMessage/delta",
                params=AgentMessageDeltaNotification(
                    thread_id="", turn_id="", item_id="msg-1", delta="Hello\nWorld\n"
                ),
            )
        )
        agent_cells = [c for c in r.state.transcript_cells if isinstance(c, AgentMessageCell)]
        assert len(agent_cells) == 2
        assert agent_cells[0].source_line == "Hello"
        assert agent_cells[0].is_first is True
        assert agent_cells[1].source_line == "World"
        assert agent_cells[1].is_first is False

    def test_agent_message_delta_incremental(self):
        r = TurnV2Renderer()
        r.handle_server_notification(
            ServerNotification(
                variant="AgentMessageDelta",
                method="item/agentMessage/delta",
                params=AgentMessageDeltaNotification(
                    thread_id="", turn_id="", item_id="msg-1", delta="Line 1\nLine "
                ),
            )
        )
        r.handle_server_notification(
            ServerNotification(
                variant="AgentMessageDelta",
                method="item/agentMessage/delta",
                params=AgentMessageDeltaNotification(
                    thread_id="", turn_id="", item_id="msg-1", delta="2\n"
                ),
            )
        )
        agent_cells = [c for c in r.state.transcript_cells if isinstance(c, AgentMessageCell)]
        assert len(agent_cells) == 2
        assert agent_cells[0].source_line == "Line 1"
        assert agent_cells[1].source_line == "Line 2"

    def test_reasoning_summary_text_delta_accumulates(self):
        r = TurnV2Renderer()
        r.handle_server_notification(
            ServerNotification(
                variant="ReasoningSummaryTextDelta",
                method="item/reasoning/summaryTextDelta",
                params={"delta": "thinking...", "itemId": "r1", "summaryIndex": 0},
            )
        )
        r.handle_server_notification(
            ServerNotification(
                variant="ReasoningSummaryTextDelta",
                method="item/reasoning/summaryTextDelta",
                params={"delta": " more", "itemId": "r1", "summaryIndex": 0},
            )
        )
        assert r.state.reasoning_buffer == "thinking... more"

    def test_reasoning_text_delta_ignored_by_default(self):
        r = TurnV2Renderer()
        r.handle_server_notification(
            ServerNotification(
                variant="ReasoningTextDelta",
                method="item/reasoning/textDelta",
                params={"delta": "raw thinking", "itemId": "r1", "contentIndex": 0},
            )
        )
        assert r.state.reasoning_buffer == ""  # ignored matching official TUI

    def test_plan_delta_goes_to_plan_stream_controller(self):
        r = TurnV2Renderer()
        r.handle_server_notification(
            ServerNotification(
                variant="PlanDelta",
                method="item/plan/delta",
                params={"delta": "# Plan\n\nStep 1", "itemId": "plan-1"},
            )
        )
        assert r.state.plan_stream_controller.raw_source == "# Plan\n\nStep 1"


class TestItemLifecycle:
    def test_item_started_command_creates_exec_cell(self):
        r = TurnV2Renderer()
        r.handle_server_notification(
            ServerNotification(
                variant="ItemStarted",
                method="item/started",
                params={
                    "threadId": "",
                    "turnId": "",
                    "item": {"type": "commandExecution", "id": "cmd-1", "command": "git status"},
                },
            )
        )
        assert isinstance(r.state.active_cell, ExecCell)
        assert r.state.active_cell.call_id == "cmd-1"
        assert r.state.active_cell.command == "git status"

    def test_item_started_mcp_creates_mcp_cell(self):
        r = TurnV2Renderer()
        r.handle_server_notification(
            ServerNotification(
                variant="ItemStarted",
                method="item/started",
                params={
                    "threadId": "",
                    "turnId": "",
                    "item": {"type": "mcpToolCall", "id": "mcp-1", "server": "filesystem", "tool": "read"},
                },
            )
        )
        assert isinstance(r.state.active_cell, McpToolCallCell)
        assert r.state.active_cell.server == "filesystem"
        assert r.state.active_cell.tool == "read"

    def test_item_started_file_change_goes_to_history(self):
        r = TurnV2Renderer()
        r.handle_server_notification(
            ServerNotification(
                variant="ItemStarted",
                method="item/started",
                params={
                    "threadId": "",
                    "turnId": "",
                    "item": {"type": "fileChange", "id": "fc-1", "changes": [{"path": "a.py", "kind": {"type": "add"}}]},
                },
            )
        )
        patch_cells = [c for c in r.state.transcript_cells if isinstance(c, PatchHistoryCell)]
        assert len(patch_cells) == 1
        assert patch_cells[0].item_id == "fc-1"

    def test_item_started_web_search_goes_to_history(self):
        r = TurnV2Renderer()
        r.handle_server_notification(
            ServerNotification(
                variant="ItemStarted",
                method="item/started",
                params={
                    "threadId": "",
                    "turnId": "",
                    "item": {"type": "webSearch", "id": "ws-1", "query": "openai codex"},
                },
            )
        )
        ws_cells = [c for c in r.state.transcript_cells if isinstance(c, WebSearchCell)]
        assert len(ws_cells) == 1
        assert ws_cells[0].query == "openai codex"

    def test_item_started_agent_message_is_skipped(self):
        r = TurnV2Renderer()
        cell_count_before = len(r.state.transcript_cells)
        r.handle_server_notification(
            ServerNotification(
                variant="ItemStarted",
                method="item/started",
                params={
                    "threadId": "",
                    "turnId": "",
                    "item": {"type": "agentMessage", "id": "am-1"},
                },
            )
        )
        assert len(r.state.transcript_cells) == cell_count_before

    def test_item_completed_command_flushes_active_cell(self):
        r = TurnV2Renderer()
        r.state.active_cell = ExecCell(call_id="cmd-1", command="ls", output="file1\nfile2")
        r.handle_server_notification(
            ServerNotification(
                variant="ItemCompleted",
                method="item/completed",
                params=ItemCompletedNotification(
                    thread_id="",
                    turn_id="",
                    item={"type": "commandExecution", "id": "cmd-1", "aggregatedOutput": "file1\nfile2\n", "exitCode": 0},
                    completed_at_ms=1000,
                ),
            )
        )
        assert r.state.active_cell is None
        exec_cells = [c for c in r.state.transcript_cells if isinstance(c, ExecCell)]
        assert len(exec_cells) == 1
        assert exec_cells[0].status == "completed"
        assert exec_cells[0].exit_code == 0

    def test_item_started_command_flushes_previous_active(self):
        r = TurnV2Renderer()
        r.state.active_cell = ExecCell(call_id="cmd-1", command="ls")
        r.handle_server_notification(
            ServerNotification(
                variant="ItemStarted",
                method="item/started",
                params={
                    "threadId": "", "turnId": "",
                    "item": {"type": "commandExecution", "id": "cmd-2", "command": "pwd"},
                },
            )
        )
        # Old active_cell should be in history
        flushed = [c for c in r.state.transcript_cells if isinstance(c, ExecCell) and c.call_id == "cmd-1"]
        assert len(flushed) == 1
        assert flushed[0].status == "completed"
        # New cell is active
        assert isinstance(r.state.active_cell, ExecCell)
        assert r.state.active_cell.call_id == "cmd-2"


class TestToolOutputDeltas:
    def test_command_output_delta_appends_to_active_cell(self):
        r = TurnV2Renderer()
        r.state.active_cell = ExecCell(call_id="cmd-1", command="ls")
        r.handle_server_notification(
            ServerNotification(
                variant="CommandExecutionOutputDelta",
                method="item/commandExecution/outputDelta",
                params={"itemId": "cmd-1", "delta": "output line\n"},
            )
        )
        assert r.state.active_cell.output == "output line\n"

    def test_command_output_delta_wrong_id_ignored(self):
        r = TurnV2Renderer()
        r.state.active_cell = ExecCell(call_id="cmd-1", command="ls")
        r.handle_server_notification(
            ServerNotification(
                variant="CommandExecutionOutputDelta",
                method="item/commandExecution/outputDelta",
                params={"itemId": "cmd-2", "delta": "wrong"},
            )
        )
        assert r.state.active_cell.output == ""

    def test_file_change_output_delta_updates_history_cell(self):
        r = TurnV2Renderer()
        r.state.add_to_history(PatchHistoryCell(item_id="fc-1"))
        r.handle_server_notification(
            ServerNotification(
                variant="FileChangeOutputDelta",
                method="item/fileChange/outputDelta",
                params={"itemId": "fc-1", "delta": "patch output"},
            )
        )
        patch_cells = [c for c in r.state.transcript_cells if isinstance(c, PatchHistoryCell)]
        assert patch_cells[0].output == "patch output"


class TestPlanAndDiff:
    def test_turn_plan_updated(self):
        r = TurnV2Renderer()
        r.handle_server_notification(
            ServerNotification(
                variant="TurnPlanUpdated",
                method="turn/plan/updated",
                params={
                    "plan": [
                        {"step": "Step 1", "status": "completed"},
                        {"step": "Step 2", "status": "inProgress"},
                        {"step": "Step 3", "status": "pending"},
                    ],
                    "explanation": "here's the plan",
                },
            )
        )
        plan_cells = [c for c in r.state.transcript_cells if isinstance(c, PlanUpdateCell)]
        assert len(plan_cells) == 1
        assert len(plan_cells[0].steps) == 3
        assert plan_cells[0].steps[0].status == "completed"
        assert plan_cells[0].steps[1].status == "in_progress"
        assert plan_cells[0].steps[2].status == "pending"

    def test_turn_diff_updated(self):
        r = TurnV2Renderer()
        r.handle_server_notification(
            ServerNotification(
                variant="TurnDiffUpdated",
                method="turn/diff/updated",
                params={"diff": "diff --git a/x b/x\n..."},
            )
        )
        assert "diff --git" in r.state.latest_diff


class TestHook:
    def test_hook_started(self):
        r = TurnV2Renderer()
        r.handle_server_notification(
            ServerNotification(
                variant="HookStarted",
                method="hook/started",
                params={"run": {"type": "PreToolUse", "name": "lint"}},
            )
        )
        assert r.state.active_hook_cell is not None
        assert r.state.active_hook_cell.status == "running"

    def test_hook_completed_flushes(self):
        r = TurnV2Renderer()
        r.state.active_hook_cell = r.state.active_hook_cell  # no-op for setup
        r.handle_server_notification(
            ServerNotification(
                variant="HookStarted",
                method="hook/started",
                params={"run": {"type": "PreToolUse"}},
            )
        )
        r.handle_server_notification(
            ServerNotification(
                variant="HookCompleted",
                method="hook/completed",
                params={"run": {"type": "PreToolUse"}},
            )
        )
        assert r.state.active_hook_cell is None
        # Should be in transcript
        assert any(
            isinstance(c, r.state.active_hook_cell.__class__)
            for c in r.state.transcript_cells
        ) or any(hasattr(c, "hook_type") for c in r.state.transcript_cells)  # at minimum, something was pushed


class TestConsolidate:
    def test_consolidate_agent_message_merges_cells(self):
        r = TurnV2Renderer()
        r.state.add_to_history(AgentMessageCell(source_line="Hello", is_first=True))
        r.state.add_to_history(AgentMessageCell(source_line="World", is_first=False))
        r.state.add_to_history(AgentMessageCell(source_line="!", is_first=False))
        r.state.consolidate_agent_message()

        # Should be 1 AgentMarkdownCell instead of 3 AgentMessageCell
        agent_cells = [c for c in r.state.transcript_cells if isinstance(c, AgentMessageCell)]
        markdown_cells = [c for c in r.state.transcript_cells if isinstance(c, AgentMarkdownCell)]
        assert len(agent_cells) == 0
        assert len(markdown_cells) == 1
        assert markdown_cells[0].source == "Hello\nWorld\n!"


class TestUnknownVariant:
    def test_unknown_variant_silently_ignored(self):
        r = TurnV2Renderer()
        cell_count = len(r.state.transcript_cells)
        r.handle_server_notification(
            ServerNotification(
                variant="ThreadStarted",
                method="thread/started",
                params={},
            )
        )
        assert len(r.state.transcript_cells) == cell_count
