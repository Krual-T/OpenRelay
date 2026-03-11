from openrelay.runtime_live import build_process_panel_text, build_reply_card


def test_build_reply_card_uses_official_complete_card_shape() -> None:
    success_card = build_reply_card("done", "openrelay 回复")

    assert success_card["schema"] == "2.0"
    assert success_card["config"]["wide_screen_mode"] is True
    assert success_card["config"]["update_multi"] is True
    assert success_card["body"]["elements"] == [{"tag": "markdown", "content": "done"}]


def test_build_reply_card_adds_collapsible_process_panel() -> None:
    card = build_reply_card("done", "openrelay 回复", process_text="**状态**\n- 正在准备回复")

    process_panel = next(element for element in card["body"]["elements"] if element.get("tag") == "collapsible_panel")
    assert process_panel["expanded"] is False
    assert process_panel["header"]["title"]["content"] == "🧾 中间过程"
    assert process_panel["elements"][0]["content"] == "**状态**\n- 正在准备回复"
    assert card["body"]["elements"][-1] == {"tag": "markdown", "content": "done"}


def test_build_process_panel_text_collects_status_command_and_reasoning() -> None:
    text = build_process_panel_text(
        {
            "history": ["正在准备回复", "完成 ls -la"],
            "commands": [{"command": "ls -la", "exitCode": 0, "outputPreview": "file1\nfile2"}],
            "reasoning_text": "先检查 runtime。",
        }
    )

    assert "**状态**" in text
    assert "- 正在准备回复" in text
    assert "**命令**" in text
    assert "- `ls -la` · exit 0" in text
    assert "输出：`file1`" in text
    assert "**补充内容**" in text
    assert "先检查 runtime。" in text


def test_build_reply_card_splits_inline_thinking_tags() -> None:
    card = build_reply_card("<think>先看 runtime</think>\n# Answer")

    reasoning_panel = next(element for element in card["body"]["elements"] if element.get("tag") == "collapsible_panel")
    assert reasoning_panel["header"]["title"]["content"] == "🧾 中间过程"
    assert reasoning_panel["elements"][0]["content"] == "先看 runtime"
    assert card["body"]["elements"][1]["content"] == "#### Answer"
