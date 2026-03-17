from openrelay.agent_runtime import (
    ApprovalRequest,
    ApprovalRequestedEvent,
    ApprovalResolvedEvent,
    AssistantDeltaEvent,
    LiveTurnRegistry,
    PlanStep,
    PlanUpdatedEvent,
    RateLimitsUpdatedEvent,
    ReasoningDeltaEvent,
    RuntimeEvent,
    SkillsUpdatedEvent,
    ThreadDiffUpdatedEvent,
    ThreadStatusUpdatedEvent,
    ToolCompletedEvent,
    ToolProgressEvent,
    ToolStartedEvent,
    ToolState,
    TurnCompletedEvent,
    TurnFailedEvent,
    TurnStartedEvent,
    UsageSnapshot,
    UsageUpdatedEvent,
)


def test_live_turn_registry_reduces_streaming_state() -> None:
    registry = LiveTurnRegistry()
    registry.apply(TurnStartedEvent(backend="codex", session_id="s1", turn_id="t1", event_type="turn.started"))
    registry.apply(AssistantDeltaEvent(backend="codex", session_id="s1", turn_id="t1", event_type="assistant.delta", delta="hel"))
    registry.apply(AssistantDeltaEvent(backend="codex", session_id="s1", turn_id="t1", event_type="assistant.delta", delta="lo"))
    registry.apply(ReasoningDeltaEvent(backend="codex", session_id="s1", turn_id="t1", event_type="reasoning.delta", text="inspect code"))
    registry.apply(
        PlanUpdatedEvent(
            backend="codex",
            session_id="s1",
            turn_id="t1",
            event_type="plan.updated",
            steps=(PlanStep("Inspect runtime", "completed"), PlanStep("Add reducer", "in_progress")),
            explanation="phase 1",
        )
    )
    registry.apply(
        ToolStartedEvent(
            backend="codex",
            session_id="s1",
            turn_id="t1",
            event_type="tool.started",
            tool=ToolState(tool_id="cmd_1", kind="command", title="Run rg", status="running", preview="rg runtime"),
        )
    )
    registry.apply(
        ToolProgressEvent(
            backend="codex",
            session_id="s1",
            turn_id="t1",
            event_type="tool.progress",
            tool_id="cmd_1",
            detail="found src/openrelay/runtime/orchestrator.py",
        )
    )
    registry.apply(
        ApprovalRequestedEvent(
            backend="codex",
            session_id="s1",
            turn_id="t1",
            event_type="approval.requested",
            request=ApprovalRequest(
                approval_id="a1",
                session_id="s1",
                turn_id="t1",
                kind="command",
                title="Command approval",
                description="Run rg",
            ),
        )
    )
    registry.apply(
        ApprovalResolvedEvent(
            backend="codex",
            session_id="s1",
            turn_id="t1",
            event_type="approval.resolved",
            approval_id="a1",
        )
    )
    registry.apply(
        ToolCompletedEvent(
            backend="codex",
            session_id="s1",
            turn_id="t1",
            event_type="tool.completed",
            tool=ToolState(
                tool_id="cmd_1",
                kind="command",
                title="Run rg",
                status="completed",
                preview="rg runtime",
                exit_code=0,
            ),
        )
    )
    registry.apply(
        UsageUpdatedEvent(
            backend="codex",
            session_id="s1",
            turn_id="t1",
            event_type="usage.updated",
            usage=UsageSnapshot(input_tokens=10, output_tokens=5, total_tokens=15),
        )
    )
    registry.apply(
        ThreadStatusUpdatedEvent(
            backend="codex",
            session_id="s1",
            turn_id="t1",
            event_type="thread.status.updated",
            status="active",
        )
    )
    registry.apply(
        RateLimitsUpdatedEvent(
            backend="codex",
            session_id="s1",
            turn_id="t1",
            event_type="rate_limits.updated",
            rate_limits={"limitId": "codex", "primary": {"usedPercent": 37}},
        )
    )
    registry.apply(
        SkillsUpdatedEvent(
            backend="codex",
            session_id="s1",
            turn_id="t1",
            event_type="skills.updated",
            version="skills-v3",
            skills=("search", "apply_patch"),
        )
    )
    registry.apply(
        ThreadDiffUpdatedEvent(
            backend="codex",
            session_id="s1",
            turn_id="t1",
            event_type="thread.diff.updated",
            diff_id="diff_9",
        )
    )
    state = registry.apply(
        TurnCompletedEvent(
            backend="codex",
            session_id="s1",
            turn_id="t1",
            event_type="turn.completed",
            final_text="hello",
        )
    )

    assert state.status == "completed"
    assert state.assistant_text == "hello"
    assert state.reasoning_text == "inspect code"
    assert [step.status for step in state.plan_steps] == ["completed", "in_progress"]
    assert state.pending_approval is None
    assert state.usage is not None and state.usage.total_tokens == 15
    assert state.thread_status == "active"
    assert state.rate_limits["limitId"] == "codex"
    assert state.skills_version == "skills-v3"
    assert state.available_skills == ("search", "apply_patch")
    assert state.last_diff_id == "diff_9"
    assert len(state.tools) == 1
    assert state.tools[0].detail == "found src/openrelay/runtime/orchestrator.py"
    assert state.tools[0].exit_code == 0


def test_live_turn_registry_ignores_unknown_event_and_merges_terminal_state() -> None:
    registry = LiveTurnRegistry()
    registry.apply(TurnStartedEvent(backend="codex", session_id="s2", turn_id="t2", event_type="turn.started"))
    registry.apply(RuntimeEvent(backend="codex", session_id="s2", turn_id="t2", event_type="provider.unknown"))
    state = registry.apply(
        TurnFailedEvent(
            backend="codex",
            session_id="s2",
            turn_id="t2",
            event_type="turn.failed",
            message="boom",
        )
    )

    assert state.status == "failed"
    assert state.error_message == "boom"
