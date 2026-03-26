from openrelay.runtime import build_activity_summary, render_live_status_markdown, render_live_status_sections
from openrelay.agent_runtime import LiveTurnViewModel
from openrelay.feishu.renderers.live_turn_renderer import FeishuLiveTurnRenderer
from openrelay.presentation.live_turn_view_builder import LiveTurnViewBuilder



def test_build_activity_summary_renders_reasoning_and_commands() -> None:
    summary = build_activity_summary(
        {
            "reasoning": [{"text": "**计划**\n先读代码"}],
            "statuses": ["准备上下文"],
            "commands": [{"command": "ls -la", "outputPreview": "total 10", "exitCode": 0}],
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }
    )
    assert "推理：计划" in summary
    assert "命令：`ls -la`" in summary
    assert "用量：in 10 · out 20" in summary



def test_render_live_status_markdown_contains_header_details_and_body() -> None:
    markdown = render_live_status_markdown(
        {
            "heading": "Running command",
            "status": "Run ls -la",
            "current_command": "ls -la",
            "partial_text": "partial reply",
            "started_at": "2026-03-09T00:00:00+00:00",
        }
    )
    assert "`Running`" in markdown
    assert "● • •" in markdown
    assert "**Running command**" in markdown
    assert "Current: running `ls -la`" in markdown
    assert "partial reply" in markdown



def test_render_live_status_sections_splits_fields() -> None:
    sections = render_live_status_sections(
        {
            "heading": "Generating reply",
            "status": "Streaming output",
            "partial_text": "hello",
        }
    )
    assert sections["header"]
    assert sections["details"]
    assert sections["body"] == "hello"
    assert "`Running`" in sections["header"]
    assert "```text" in sections["details"]


def test_render_live_status_sections_show_reasoning_when_answer_not_started() -> None:
    sections = render_live_status_sections(
        {
            "heading": "Analyzing",
            "status": "Planning next step",
            "reasoning_text": "先检查 runtime 和 card 渲染。",
        }
    )

    assert "💭 **Thinking...**" in sections["body"]
    assert "先检查 runtime 和 card 渲染。" in sections["body"]


def test_live_turn_builder_and_renderer_accept_typed_view_model() -> None:
    builder = LiveTurnViewBuilder()
    renderer = FeishuLiveTurnRenderer()
    view = builder.build_snapshot(
        LiveTurnViewModel(
            backend="codex",
            session_id="relay_1",
            native_session_id="thread_1",
            turn_id="turn_1",
            status="running",
            assistant_text="partial answer",
        )
    )

    transcript = builder.build_transcript_markdown(view)
    card = renderer.build_final_card(view, fallback_text="fallback")

    assert transcript.endswith("---\n\npartial answer")
    assert card["body"]["elements"]
