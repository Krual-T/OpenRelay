"""测试 cell 数据模型和 cell → markdown 渲染。"""

from openrelay.presentation.v2_renderer.cell_renderer import (
    render_agent_markdown_cell,
    render_collab_agent_cell,
    render_error_cell,
    render_exec_cell,
    render_final_separator_cell,
    render_hook_cell,
    render_mcp_tool_call_cell,
    render_patch_history_cell,
    render_plan_update_cell,
    render_proposed_plan_cell,
    render_reasoning_cell,
    render_warning_cell,
    render_web_search_cell,
)
from openrelay.presentation.v2_renderer.cells import (
    AgentMarkdownCell,
    CollabAgentCell,
    ErrorCell,
    ExecCell,
    FinalSeparatorCell,
    HookCell,
    McpToolCallCell,
    PatchHistoryCell,
    PlanStepItem,
    PlanUpdateCell,
    ProposedPlanCell,
    ReasoningCell,
    WarningCell,
    WebSearchCell,
)


class TestExecCell:
    def test_completed_success(self):
        cell = ExecCell(call_id="c1", command="git status", output="On branch main", exit_code=0, status="completed")
        rendered = render_exec_cell(cell, running=False)
        assert "Ran" in rendered
        assert "git" in rendered
        assert "status" in rendered

    def test_completed_failure(self):
        cell = ExecCell(call_id="c1", command="bad", output="error", exit_code=1, status="completed")
        rendered = render_exec_cell(cell, running=False)
        assert "exit 1" in rendered

    def test_running_shows_spinner(self):
        cell = ExecCell(call_id="c1", command="sleep 10", status="running")
        rendered = render_exec_cell(cell, running=True, spinner_frame=0)
        assert "● • •" in rendered
        assert "Running" in rendered

    def test_exploration_mode(self):
        cell = ExecCell(call_id="c1", command="rg pattern", exploration=True, status="completed")
        rendered = render_exec_cell(cell, running=False)
        assert "Search" in rendered

    def test_output_truncated(self):
        lines = "\n".join(f"line {i}" for i in range(20))
        cell = ExecCell(call_id="c1", command="cmd", output=lines, status="completed")
        rendered = render_exec_cell(cell, running=False)
        assert "... +" in rendered  # truncation marker


class TestMcpToolCallCell:
    def test_completed(self):
        cell = McpToolCallCell(call_id="m1", server="filesystem", tool="read", status="completed")
        rendered = render_mcp_tool_call_cell(cell, running=False)
        assert "Called" in rendered
        assert "filesystem" in rendered
        assert "read" in rendered

    def test_running(self):
        cell = McpToolCallCell(call_id="m1", server="fs", tool="write", status="running")
        rendered = render_mcp_tool_call_cell(cell, running=True, spinner_frame=1)
        assert "Calling" in rendered


class TestPatchHistoryCell:
    def test_file_changes(self):
        cell = PatchHistoryCell(
            item_id="fc1",
            changes=[{"path": "src/a.py", "kind": {"type": "add"}}, {"path": "src/b.py", "kind": {"type": "update"}}],
            status="completed",
        )
        rendered = render_patch_history_cell(cell, running=False)
        assert "Updated files" in rendered
        assert "src/a.py" in rendered
        assert "src/b.py" in rendered

    def test_running(self):
        cell = PatchHistoryCell(item_id="fc1", status="running")
        rendered = render_patch_history_cell(cell, running=True, spinner_frame=0)
        assert "Updating files" in rendered


class TestWebSearchCell:
    def test_completed(self):
        cell = WebSearchCell(item_id="ws1", query="codex", status="completed")
        rendered = render_web_search_cell(cell, running=False)
        assert "Searched web" in rendered
        assert "codex" in rendered

    def test_running(self):
        cell = WebSearchCell(item_id="ws1", query="codex", status="running")
        rendered = render_web_search_cell(cell, running=True, spinner_frame=0)
        assert "Searching web" in rendered


class TestCollabAgentCell:
    def test_basic(self):
        cell = CollabAgentCell(item_id="ca1", tool="AgentX", prompt="do something", targets=["t1", "t2"], status="running")
        rendered = render_collab_agent_cell(cell, running=True, spinner_frame=0)
        assert "AgentX" in rendered

    def test_completed(self):
        cell = CollabAgentCell(item_id="ca1", tool="AgentX", status="completed")
        rendered = render_collab_agent_cell(cell, running=False)
        assert "Updated agent" in rendered


class TestReasoningCell:
    def test_reasoning(self):
        cell = ReasoningCell(text="Let me think about this...")
        rendered = render_reasoning_cell(cell)
        assert "Thinking" in rendered
        assert "Let me think" in rendered


class TestHookCell:
    def test_running(self):
        cell = HookCell(hook_type="PreToolUse", status="running")
        rendered = render_hook_cell(cell, running=True, spinner_frame=0)
        assert "Running" in rendered

    def test_completed(self):
        cell = HookCell(hook_type="PreToolUse", status="completed")
        rendered = render_hook_cell(cell, running=False)
        assert "Completed" in rendered
        assert "PreToolUse" in rendered


class TestPlanCells:
    def test_plan_update(self):
        cell = PlanUpdateCell(
            steps=[
                PlanStepItem(step="Step 1", status="completed"),
                PlanStepItem(step="Step 2", status="in_progress"),
                PlanStepItem(step="Step 3", status="pending"),
            ],
            explanation="the plan",
        )
        rendered = render_plan_update_cell(cell)
        assert "Updated Plan" in rendered
        assert "Step 1" in rendered
        assert "Step 2" in rendered

    def test_proposed_plan(self):
        cell = ProposedPlanCell(source="# Plan\n\nContent")
        rendered = render_proposed_plan_cell(cell)
        assert "Proposed Plan" in rendered


class TestNotificationCells:
    def test_warning(self):
        cell = WarningCell(message="something wrong")
        rendered = render_warning_cell(cell)
        assert "something wrong" in rendered

    def test_error(self):
        cell = ErrorCell(message="fatal error")
        rendered = render_error_cell(cell)
        assert "fatal error" in rendered


class TestFinalSeparator:
    def test_with_duration(self):
        cell = FinalSeparatorCell(elapsed_seconds=90.0)
        rendered = render_final_separator_cell(cell)
        assert "Worked for" in rendered
        assert "1m 30s" in rendered

    def test_short_duration(self):
        cell = FinalSeparatorCell(elapsed_seconds=10.0)
        rendered = render_final_separator_cell(cell)
        # Under 60s, no "Worked for" text
        assert "Worked for" not in rendered


class TestAgentCells:
    def test_agent_markdown(self):
        cell = AgentMarkdownCell(source="Hello **World**")
        rendered = render_agent_markdown_cell(cell)
        assert "Hello **World**" in rendered
