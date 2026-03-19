from tests.feishu.streaming_support import build_complete_card, optimize_markdown_style

def test_build_complete_card_prefers_transcript_markdown() -> None:
    card = build_complete_card(
        "最终答案",
        transcript_markdown="• **Ran** `pytest`\n\n---\n\n最终答案",
    )

    assert card["body"]["elements"] == [{"tag": "markdown", "content": "• **Ran** `pytest`\n\n---\n\n最终答案"}]
    assert "summary" not in card["config"]


def test_optimize_markdown_style_replaces_inline_code_with_feishu_color_enum() -> None:
    rendered = optimize_markdown_style("执行 `pytest -q`，查看 `src/openrelay/feishu/highlight.py`。")

    assert "`pytest -q`" not in rendered
    assert "<font color='blue'>pytest&nbsp;-q</font>" in rendered
    assert "<font color='blue'>src/openrelay/feishu/highlight.py</font>" in rendered


def test_optimize_markdown_style_keeps_code_fence_untouched_while_restyling_inline_code() -> None:
    rendered = optimize_markdown_style("先看 `uv run pytest`\n\n```bash\npytest -q\n```")

    assert "<font color='blue'>uv&nbsp;run&nbsp;pytest</font>" in rendered
    assert "```bash\npytest -q\n```" in rendered


def test_build_complete_card_renders_answer_only_without_transcript() -> None:
    card = build_complete_card("最终答案")

    assert card["body"]["elements"] == [{"tag": "markdown", "content": "最终答案"}]
    assert "summary" not in card["config"]


def test_build_complete_card_uses_collapsible_panel_when_panel_text_provided() -> None:
    card = build_complete_card("最终答案", panel_text="• **Ran** `pytest -q`")

    assert card["body"]["elements"][0]["tag"] == "collapsible_panel"
    assert card["body"]["elements"][0]["header"]["title"]["content"] == "Execution Log"
    assert card["body"]["elements"][0]["elements"][0]["content"] == "• **Ran** `pytest -q`"
    assert card["body"]["elements"][1] == {"tag": "markdown", "content": "最终答案"}
    assert "summary" not in card["config"]
