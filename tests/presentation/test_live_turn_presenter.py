from openrelay.agent_runtime import ApprovalDecision, ApprovalRequest, BackendEventRecord, CommentaryRecord, LiveTurnViewModel, PlanStep, TerminalInteraction, ToolState
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
        commentary=(
            CommentaryRecord(item_id="c1", text="progress update", status="running"),
        ),
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
    commentary_item = next(item for item in snapshot["history_items"] if item["type"] == "commentary")
    assert commentary_item["text"] == "progress update"
    assert "Command Approval Required" in process_text
    assert "Search runtime" in process_text


def test_live_turn_presenter_keeps_running_commentary_out_of_history_items() -> None:
    presenter = LiveTurnPresenter()
    state = LiveTurnViewModel(
        backend="codex",
        session_id="relay_1",
        native_session_id="thread_1",
        turn_id="turn_1",
        status="running",
        commentary=(
            CommentaryRecord(item_id="c1", text="我用 using-openharness 做了最小入口检查。", status="running"),
        ),
        tools=(
            ToolState(
                tool_id="search_1",
                kind="web_search",
                title="Searching web",
                status="running",
                preview="openharness skill",
                detail="",
            ),
        ),
    )

    snapshot = presenter.build_snapshot(state)

    commentary_item = next(item for item in snapshot["history_items"] if item["type"] == "commentary")
    assert snapshot["partial_text"] == ""
    assert commentary_item["state"] == "running"
    assert commentary_item["text"] == "我用 using-openharness 做了最小入口检查。"


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
        latest_diff="--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new",
    )

    snapshot = presenter.build_snapshot(state)
    system_items = [item for item in snapshot["history_items"] if item["type"] == "system"]

    assert system_items == []


def test_live_turn_presenter_preserves_file_change_diff_detail() -> None:
    presenter = LiveTurnPresenter()
    state = LiveTurnViewModel(
        backend="codex",
        session_id="relay_1",
        native_session_id="thread_1",
        turn_id="turn_1",
        status="running",
        tools=(
            ToolState(
                tool_id="fc_1",
                kind="file_change",
                title="File changes",
                status="completed",
                preview="src/openrelay/feishu/reply_card.py",
                detail="--- a/src/openrelay/feishu/reply_card.py\n+++ b/src/openrelay/feishu/reply_card.py\n@@ -1 +1 @@\n-old line\n+new line",
                provider_payload={
                    "changes": [
                        {
                            "path": "src/openrelay/feishu/reply_card.py",
                            "kind": {"type": "update"},
                        }
                    ]
                },
            ),
        ),
    )

    snapshot = presenter.build_snapshot(state)
    file_change = next(item for item in snapshot["history_items"] if item["type"] == "file_change")

    assert file_change["detail"].startswith("--- a/src/openrelay/feishu/reply_card.py")


def test_live_turn_presenter_builds_final_card_with_commentary_as_static_transcript_item() -> None:
    presenter = LiveTurnPresenter()
    state = LiveTurnViewModel(
        backend="codex",
        session_id="relay_1",
        native_session_id="thread_1",
        turn_id="turn_1",
        status="completed",
        commentary=(
            CommentaryRecord(item_id="c1", text="先按仓库协议把上下文跑一遍。", status="completed"),
        ),
        assistant_text="最终答案",
        tools=(
            ToolState(
                tool_id="cmd_1",
                kind="command",
                title="rg runtime",
                status="completed",
                preview="rg runtime",
                detail="src/openrelay/runtime",
            ),
        ),
    )

    card = presenter.build_final_card(state)
    elements = card["body"]["elements"]
    panel = elements[0]
    answer = elements[1]

    assert panel["tag"] == "collapsible_panel"
    assert "Ran" in panel["elements"][0]["content"]
    assert "---" in panel["elements"][0]["content"]
    assert "• 先按仓库协议把上下文跑一遍。" in panel["elements"][0]["content"]
    assert "进展" not in panel["elements"][0]["content"]
    assert "Update" not in panel["elements"][0]["content"]
    assert "•••" not in panel["elements"][0]["content"]
    assert answer == {"tag": "markdown", "content": "最终答案"}


def test_live_turn_presenter_builds_final_card_with_multiple_commentary_items() -> None:
    presenter = LiveTurnPresenter()
    state = LiveTurnViewModel(
        backend="codex",
        session_id="relay_1",
        native_session_id="thread_1",
        turn_id="turn_1",
        status="completed",
        commentary=(
            CommentaryRecord(item_id="c1", text="我先走 using-openharness，再查事实来源。", status="completed"),
            CommentaryRecord(item_id="c2", text="入口流程确认了。现在做概念和仓库对照调研。", status="completed"),
            CommentaryRecord(item_id="c3", text="结论已经够了，我补一下精确文件位置。", status="completed"),
        ),
        assistant_text="最终答案",
    )

    card = presenter.build_final_card(state)
    panel_content = card["body"]["elements"][0]["elements"][0]["content"]

    assert panel_content.count("---") >= 3
    assert "进展" not in panel_content
    assert "• 我先走 using-openharness，再查事实来源。" in panel_content
    assert "• 入口流程确认了。现在做概念和仓库对照调研。" in panel_content
    assert "• 结论已经够了，我补一下精确文件位置。" in panel_content
    assert panel_content.index("• 我先走 using-openharness，再查事实来源。") < panel_content.index("• 入口流程确认了。现在做概念和仓库对照调研。")
    assert panel_content.index("• 入口流程确认了。现在做概念和仓库对照调研。") < panel_content.index("• 结论已经够了，我补一下精确文件位置。")


def test_live_turn_presenter_uses_latest_turn_diff_when_file_change_detail_is_empty() -> None:
    presenter = LiveTurnPresenter()
    state = LiveTurnViewModel(
        backend="codex",
        session_id="relay_1",
        native_session_id="thread_1",
        turn_id="turn_1",
        status="running",
        latest_diff="--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new",
        tools=(
            ToolState(
                tool_id="fc_1",
                kind="file_change",
                title="File changes",
                status="completed",
                preview="foo.py",
                detail="",
                provider_payload={
                    "changes": [
                        {
                            "path": "foo.py",
                            "kind": {"type": "update"},
                        }
                    ]
                },
            ),
        ),
    )

    snapshot = presenter.build_snapshot(state)
    file_change = next(item for item in snapshot["history_items"] if item["type"] == "file_change")

    assert file_change["detail"] == "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new"


def test_live_turn_presenter_prefers_latest_turn_diff_over_plain_file_change_output() -> None:
    presenter = LiveTurnPresenter()
    state = LiveTurnViewModel(
        backend="codex",
        session_id="relay_1",
        native_session_id="thread_1",
        turn_id="turn_1",
        status="running",
        latest_diff="--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new",
        tools=(
            ToolState(
                tool_id="fc_1",
                kind="file_change",
                title="File changes",
                status="completed",
                preview="foo.py",
                detail="Success. Updated the following files:\nM foo.py",
                provider_payload={
                    "changes": [
                        {
                            "path": "foo.py",
                            "kind": {"type": "update"},
                        }
                    ]
                },
            ),
        ),
    )

    snapshot = presenter.build_snapshot(state)
    file_change = next(item for item in snapshot["history_items"] if item["type"] == "file_change")

    assert file_change["detail"] == "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new"

def test_live_turn_presenter_preserves_plan_history_in_transcript() -> None:
    presenter = LiveTurnPresenter()
    first_state = LiveTurnViewModel(
        backend="codex",
        session_id="relay_1",
        native_session_id="thread_1",
        turn_id="turn_1",
        status="running",
        plan_steps=(
            PlanStep(step="Inspect runtime", status="completed"),
            PlanStep(step="Adjust Feishu rendering", status="in_progress"),
        ),
    )
    second_state = LiveTurnViewModel(
        backend="codex",
        session_id="relay_1",
        native_session_id="thread_1",
        turn_id="turn_1",
        status="running",
        plan_steps=(
            PlanStep(step="Inspect runtime", status="completed"),
            PlanStep(step="Adjust Feishu rendering", status="completed"),
            PlanStep(step="Verify snapshot output", status="in_progress"),
        ),
    )

    first_snapshot = presenter.build_snapshot(first_state)
    second_snapshot = presenter.build_snapshot(second_state, previous=first_snapshot)
    transcript = presenter.build_transcript_markdown(second_snapshot)

    assert len(second_snapshot["plan_history_items"]) == 2
    assert transcript.count("🟣 **Plan**") == 2
    assert "🟣 **Plan**  \n│  \n● ~~Inspect runtime~~" in transcript
    assert "Adjust Feishu rendering" in transcript
    assert "Verify snapshot output" in transcript


def test_live_turn_presenter_interleaves_plan_history_with_command_timeline() -> None:
    presenter = LiveTurnPresenter()
    first_state = LiveTurnViewModel(
        backend="codex",
        session_id="relay_1",
        native_session_id="thread_1",
        turn_id="turn_1",
        status="running",
        tools=(
            ToolState(
                tool_id="cmd_1",
                kind="command",
                title="rg runtime",
                status="completed",
                preview="rg runtime",
                detail="src/openrelay/runtime",
            ),
        ),
        plan_steps=(
            PlanStep(step="Inspect runtime", status="completed"),
            PlanStep(step="Adjust Feishu rendering", status="in_progress"),
        ),
    )
    second_state = LiveTurnViewModel(
        backend="codex",
        session_id="relay_1",
        native_session_id="thread_1",
        turn_id="turn_1",
        status="running",
        tools=(
            ToolState(
                tool_id="cmd_1",
                kind="command",
                title="rg runtime",
                status="completed",
                preview="rg runtime",
                detail="src/openrelay/runtime",
            ),
            ToolState(
                tool_id="cmd_2",
                kind="command",
                title="sed file",
                status="completed",
                preview="sed -n '1,40p' src/openrelay/feishu/reply_card.py",
                detail="def render_transcript_markdown",
            ),
        ),
        plan_steps=(
            PlanStep(step="Inspect runtime", status="completed"),
            PlanStep(step="Adjust Feishu rendering", status="completed"),
            PlanStep(step="Verify snapshot output", status="in_progress"),
        ),
    )

    first_snapshot = presenter.build_snapshot(first_state)
    second_snapshot = presenter.build_snapshot(second_state, previous=first_snapshot)

    assert [item["type"] for item in second_snapshot["transcript_items"]] == ["command", "plan", "command", "plan"]


def test_live_turn_presenter_builds_final_card_with_collapsed_execution_log() -> None:
    presenter = LiveTurnPresenter()
    state = LiveTurnViewModel(
        backend="codex",
        session_id="relay_1",
        native_session_id="thread_1",
        turn_id="turn_1",
        status="completed",
        assistant_text="最终答案",
        tools=(
            ToolState(
                tool_id="cmd_1",
                kind="command",
                title="pytest",
                status="completed",
                preview="pytest -q",
                detail="1 passed",
            ),
        ),
    )

    card = presenter.build_final_card(state)

    assert card["body"]["elements"][0]["tag"] == "collapsible_panel"
    assert card["body"]["elements"][0]["header"]["title"]["content"] == "Execution Log"
    assert "pytest" in card["body"]["elements"][0]["elements"][0]["content"]
    assert card["body"]["elements"][1] == {"tag": "markdown", "content": "最终答案"}
