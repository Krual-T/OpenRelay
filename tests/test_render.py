from openrelay.render import build_activity_summary, render_live_status_markdown, render_live_status_sections



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
            "heading": "正在执行命令",
            "status": "执行 ls -la",
            "current_command": "ls -la",
            "partial_text": "partial reply",
            "started_at": "2026-03-09T00:00:00+00:00",
        }
    )
    assert "**正在执行命令**" in markdown
    assert "当前：执行 `ls -la`" in markdown
    assert "partial reply" in markdown



def test_render_live_status_sections_splits_fields() -> None:
    sections = render_live_status_sections(
        {
            "heading": "正在生成回复",
            "status": "正在输出内容",
            "partial_text": "hello",
        }
    )
    assert sections["header"]
    assert sections["details"]
    assert sections["body"] == "hello"
