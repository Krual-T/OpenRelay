from openrelay.runtime_live import apply_live_progress, build_process_panel_text, build_reply_card


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
            "history_items": [
                {"type": "status", "state": "completed", "title": "Starting Codex", "detail": "Preparing reply"},
                {"type": "reasoning", "state": "completed", "title": "Thought for 1.2s", "text": "先检查 runtime。\n再看 card 渲染。"},
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Explored codebase",
                    "mode": "exploration",
                    "command": "ls -la",
                    "exit_code": 0,
                    "output_preview": "file1\nfile2",
                },
            ],
            "started_at": "2026-03-11T00:00:00+00:00",
        }
    )

    assert "• **Starting Codex**" in text
    assert "└ Preparing reply" in text
    assert "• **Thought for 1.2s**" in text
    assert "├ 先检查 runtime。" in text
    assert "└ 再看 card 渲染。" in text
    assert "🔵 **Explored**" in text
    assert "├ ls -la" in text
    assert "├ `file1`" in text
    assert "└ `file2`" in text
    assert "Worked for" in text


def test_build_process_panel_text_marks_failed_command_with_red_dot() -> None:
    text = build_process_panel_text(
        {
            "history_items": [
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Ran shell command",
                    "mode": "command",
                    "command": "pytest",
                    "exit_code": 1,
                    "output_preview": "1 failed\nAssertionError",
                },
            ]
        }
    )

    assert "🔴 **Ran** `pytest`" in text
    assert "├ exit 1" in text
    assert "├ `1 failed`" in text
    assert "└ `AssertionError`" in text


def test_apply_live_progress_accumulates_codex_style_history_items() -> None:
    state = {
        "history": [],
        "history_items": [],
        "commands": [],
        "heading": "",
        "status": "",
        "current_command": "",
        "last_command": None,
        "last_reasoning": "",
        "reasoning_text": "",
        "reasoning_started_at": "",
        "reasoning_elapsed_ms": 0,
        "partial_text": "",
        "spinner_frame": 0,
        "started_at": "2026-03-11T00:00:00+00:00",
    }

    apply_live_progress(state, {"type": "run.started"})
    apply_live_progress(state, {"type": "reasoning.started"})
    apply_live_progress(state, {"type": "reasoning.delta", "text": "先检查 runtime。"})
    apply_live_progress(state, {"type": "command.started", "command": {"id": "c1", "command": "rg -n runtime_live src/openrelay"}})
    apply_live_progress(
        state,
        {
            "type": "command.completed",
            "command": {
                "id": "c1",
                "command": "rg -n runtime_live src/openrelay",
                "exitCode": 0,
                "outputPreview": "src/openrelay/runtime_live.py:1",
            },
        },
    )

    items = state["history_items"]
    assert items[0]["title"] == "Starting Codex"
    assert items[1]["title"] == "Thought"
    assert items[2]["title"] == "Explored codebase"
    assert items[2]["command"] == "rg -n runtime_live src/openrelay"


def test_build_reply_card_splits_inline_thinking_tags() -> None:
    card = build_reply_card("<think>先看 runtime</think>\n# Answer")

    reasoning_panel = next(element for element in card["body"]["elements"] if element.get("tag") == "collapsible_panel")
    assert reasoning_panel["header"]["title"]["content"] == "🧾 中间过程"
    assert reasoning_panel["elements"][0]["content"] == "先看 runtime"
    assert card["body"]["elements"][1]["content"] == "#### Answer"
