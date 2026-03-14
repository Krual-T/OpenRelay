from openrelay.runtime import build_activity_summary, render_live_status_markdown, render_live_status_sections



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
    assert "⚪ ◯ ◯" in markdown
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
