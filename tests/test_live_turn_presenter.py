from openrelay.agent_runtime import ApprovalRequest, LiveTurnViewModel, PlanStep, ToolState
from openrelay.presentation.live_turn import LiveTurnPresenter


def test_live_turn_presenter_builds_snapshot_from_view_model() -> None:
    presenter = LiveTurnPresenter()
    state = LiveTurnViewModel(
        backend="codex",
        session_id="relay_1",
        native_session_id="thread_1",
        turn_id="turn_1",
        status="running",
        assistant_text="partial answer",
        reasoning_text="inspect runtime first",
        plan_steps=(PlanStep(step="Inspect runtime", status="completed"),),
        tools=(
            ToolState(
                tool_id="cmd_1",
                kind="command",
                title="rg runtime",
                status="running",
                preview="rg runtime",
                detail="src/openrelay/runtime",
            ),
        ),
        pending_approval=ApprovalRequest(
            approval_id="approval_1",
            session_id="relay_1",
            turn_id="turn_1",
            kind="command",
            title="Command Approval Required",
            description="Command: pytest -q",
        ),
    )

    snapshot = presenter.build_snapshot(state, previous={"started_at": "2026-03-16T00:00:00+00:00"})
    process_text = presenter.build_process_text(snapshot)

    assert snapshot["heading"] == "Waiting for approval"
    assert snapshot["partial_text"] == "partial answer"
    assert any(item["type"] == "command" for item in snapshot["history_items"])
    assert any(item["type"] == "reasoning" for item in snapshot["history_items"])
    assert any(item["type"] == "interaction" for item in snapshot["history_items"])
    assert "Command Approval Required" in process_text
    assert "Search runtime" in process_text
