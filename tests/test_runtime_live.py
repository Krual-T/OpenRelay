from openrelay.runtime_live import build_reply_card


def test_build_reply_card_uses_official_complete_card_shape() -> None:
    success_card = build_reply_card("done", "openrelay 回复")

    assert success_card["schema"] == "2.0"
    assert success_card["config"]["wide_screen_mode"] is True
    assert success_card["config"]["update_multi"] is True
    assert success_card["body"]["elements"] == [{"tag": "markdown", "content": "done"}]


def test_build_reply_card_adds_collapsible_reasoning_panel() -> None:
    card = build_reply_card("done", "openrelay 回复", reasoning_text="先读代码", reasoning_elapsed_ms=12000)

    reasoning_panel = next(element for element in card["body"]["elements"] if element.get("tag") == "collapsible_panel")
    assert reasoning_panel["expanded"] is False
    assert reasoning_panel["header"]["title"]["content"] == "💭 Thought for 12.0s"
    assert reasoning_panel["elements"][0]["content"] == "先读代码"
    assert card["body"]["elements"][-1] == {"tag": "markdown", "content": "done"}


def test_build_reply_card_adds_tool_summary_in_official_style() -> None:
    card = build_reply_card(
        "done",
        "openrelay 回复",
        commands=[
            {"command": "ls -la", "exitCode": 0},
            {"command": "pytest", "exitCode": 1},
        ],
    )

    assert card["body"]["elements"][0] == {"tag": "markdown", "content": "done"}
    assert card["body"]["elements"][1]["tag"] == "markdown"
    assert "✅ **ls -la** - complete" in card["body"]["elements"][1]["content"]
    assert "❌ **pytest** - failed" in card["body"]["elements"][1]["content"]


def test_build_reply_card_splits_inline_thinking_tags() -> None:
    card = build_reply_card("<think>先看 runtime</think>\n# Answer")

    reasoning_panel = next(element for element in card["body"]["elements"] if element.get("tag") == "collapsible_panel")
    assert reasoning_panel["elements"][0]["content"] == "先看 runtime"
    assert card["body"]["elements"][1]["content"] == "#### Answer"
