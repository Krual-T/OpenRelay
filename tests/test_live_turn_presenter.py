from openrelay.agent_runtime import ApprovalDecision, ApprovalRequest, BackendEventRecord, LiveTurnViewModel, PlanStep, ToolState
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
    plan_item = next(item for item in snapshot["history_items"] if item["type"] == "plan")
    assert plan_item["steps"] == [{"step": "Inspect runtime", "status": "completed"}]
    assert "Command Approval Required" in process_text
    assert "Search runtime" in process_text


def test_live_turn_presenter_builds_approval_resolved_snapshot() -> None:
    presenter = LiveTurnPresenter()
    request = ApprovalRequest(
        approval_id="approval_1",
        session_id="relay_1",
        turn_id="turn_1",
        kind="command",
        title="Command Approval Required",
        description="Command: pytest -q",
    )

    snapshot = presenter.build_approval_resolved_snapshot(
        {
            "history_items": [
                {
                    "type": "interaction",
                    "state": "running",
                    "interaction_id": "approval_1",
                    "title": "Command Approval Required",
                    "detail": "Command: pytest -q",
                }
            ],
            "heading": "Waiting for approval",
            "status": "Command Approval Required",
        },
        request,
        ApprovalDecision(decision="accept"),
    )

    assert snapshot["heading"] == "Resuming"
    assert snapshot["status"] == "Approval accepted"
    interaction = snapshot["history_items"][0]
    assert interaction["state"] == "completed"
    assert interaction["detail"] == "Approval accepted"


def test_live_turn_presenter_preserves_resolved_interaction_when_state_clears_pending_approval() -> None:
    presenter = LiveTurnPresenter()
    state = LiveTurnViewModel(
        backend="codex",
        session_id="relay_1",
        native_session_id="thread_1",
        turn_id="turn_1",
        status="running",
    )

    snapshot = presenter.build_snapshot(
        state,
        previous={
            "history_items": [
                {
                    "type": "interaction",
                    "state": "completed",
                    "interaction_id": "approval_1",
                    "title": "Command Approval Required",
                    "detail": "Approval accepted",
                }
            ]
        },
    )

    assert snapshot["history_items"][0]["type"] == "interaction"
    assert snapshot["history_items"][0]["state"] == "completed"
    assert snapshot["history_items"][0]["detail"] == "Approval accepted"


def test_live_turn_presenter_updates_native_session_and_spinner() -> None:
    presenter = LiveTurnPresenter()
    snapshot = presenter.with_native_session_id({"spinner_frame": 1}, "thread_2")
    bumped = presenter.bump_spinner(snapshot)

    assert snapshot["native_session_id"] == "thread_2"
    assert bumped["spinner_frame"] == 2


def test_live_turn_presenter_renders_unexpected_backend_event_payload() -> None:
    presenter = LiveTurnPresenter()
    state = LiveTurnViewModel(
        backend="codex",
        session_id="relay_1",
        native_session_id="thread_1",
        turn_id="turn_1",
        status="running",
        backend_events=(
            BackendEventRecord(
                event_type="backend.notice",
                title="Unexpected backend event: item/unknownEvent",
                detail="Unexpected backend event: item/unknownEvent",
                raw_payload={
                    "raw_event": {
                        "method": "item/unknownEvent",
                        "params": {"foo": "bar"},
                    }
                },
            ),
        ),
    )

    snapshot = presenter.build_snapshot(state)
    backend_event = next(item for item in snapshot["history_items"] if item["type"] == "backend_event")

    assert backend_event["title"] == "Unexpected backend event: item/unknownEvent"
    assert '"foo": "bar"' in backend_event["detail"]


def test_live_turn_presenter_renders_system_state_items() -> None:
    presenter = LiveTurnPresenter()
    state = LiveTurnViewModel(
        backend="codex",
        session_id="relay_1",
        native_session_id="thread_1",
        turn_id="turn_1",
        status="running",
        thread_status="active",
        rate_limits={"limitId": "codex", "primary": {"usedPercent": 37}},
        skills_version="skills-v3",
        available_skills=("search", "apply_patch"),
        last_diff_id="diff_9",
    )

    snapshot = presenter.build_snapshot(state)
    system_items = [item for item in snapshot["history_items"] if item["type"] == "system"]

    assert any(item["title"] == "Thread status" and item["detail"] == "active" for item in system_items)
    assert any(item["title"] == "Rate limits" and "codex: 37%" in item["detail"] for item in system_items)
    assert any(item["title"] == "Available skills" and "skills-v3: search, apply_patch" == item["detail"] for item in system_items)
    assert any(item["title"] == "Thread diff" and item["detail"] == "diff_9" for item in system_items)
