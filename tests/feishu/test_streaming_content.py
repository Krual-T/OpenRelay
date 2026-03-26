from tests.support.feishu_streaming import (
    LiveTurnPresenter,
    LiveTurnViewModel,
    STREAMING_ELEMENT_ID,
    ToolState,
    build_streaming_content,
    build_streaming_card_json,
    pytest,
    render_command_chunks,
    summarize_text_entities,
)

def test_build_streaming_card_json_uses_single_streaming_element() -> None:
    card = build_streaming_card_json()

    assert card["schema"] == "2.0"
    assert card["config"]["streaming_mode"] is True
    assert "summary" not in card["config"]
    assert card["body"]["elements"][0]["element_id"] == STREAMING_ELEMENT_ID
    assert card["body"]["elements"][0]["content"] == ""
    assert len(card["body"]["elements"]) == 1


def test_build_streaming_card_json_keeps_single_streaming_element_when_answer_starts() -> None:
    card = build_streaming_card_json(
        {
            "history_items": [
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Explored codebase",
                    "mode": "exploration",
                    "command": "rg -n Voyager",
                    "exit_code": 0,
                    "output_preview": "Gemini Voyager",
                }
            ],
            "started_at": "2026-03-11T00:00:00+00:00",
            "partial_text": "# Answer\n找到结果。",
        }
    )

    assert card["config"]["streaming_mode"] is True
    assert "summary" not in card["config"]
    assert card["body"]["elements"][0]["element_id"] == STREAMING_ELEMENT_ID
    assert "🔵 Explored" in card["body"]["elements"][0]["content"]
    assert "#### Answer\n找到结果。" in card["body"]["elements"][0]["content"]
    assert len(card["body"]["elements"]) == 1


def test_build_streaming_card_json_renders_running_loading_dots() -> None:
    card = build_streaming_card_json(
        {
            "history_items": [
                {
                    "type": "web_search",
                    "state": "running",
                    "title": "Searching web",
                    "search_id": "search_1",
                    "query": "feishu markdown loading icon",
                    "queries": ["feishu markdown loading icon"],
                }
            ],
            "spinner_frame": 1,
        }
    )

    content = str(card["body"]["elements"][0]["content"])

    assert len(card["body"]["elements"]) == 1
    assert "Searching" in content
    assert "• ● •" in content


def test_build_streaming_card_json_preserves_nbsp_entities_for_indented_output(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")

    card = build_streaming_card_json(
        {
            "history_items": [
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Ran shell command",
                    "mode": "command",
                    "command": "sed -n '430,435p' src/openrelay/runtime/command_router.py",
                    "exit_code": 0,
                    "output_preview": "        try:\n            return raw",
                }
            ]
        }
    )

    content = str(card["body"]["elements"][0]["content"])
    summary = summarize_text_entities(content)

    assert "&nbsp;&nbsp;&nbsp;&nbsp;" in content
    assert summary["nbsp_entity_count"] >= 20
    assert summary["nbsp_char_count"] == 0
    assert any("streaming content rendered" in record.getMessage() for record in caplog.records)
    assert any("streaming card json content" in record.getMessage() for record in caplog.records)


def test_build_streaming_content_prefers_partial_text_then_reasoning() -> None:
    assert build_streaming_content({"partial_text": "# Title\ncontent"}) == "---\n\n#### Title\ncontent"
    assert build_streaming_content({"partial_text": "<think>先看代码</think>\n答案"}) == "---\n\n💭 **Thinking...**\n\n先看代码\n\n---\n\n答案"
    reasoning_content = build_streaming_content(
        {
            "history_items": [
                {"type": "reasoning", "state": "running", "title": "Thinking", "text": "先看代码"},
            ],
            "started_at": "2026-03-11T00:00:00+00:00",
        }
    )
    assert "● • • Thinking" in reasoning_content
    assert "先看代码" in reasoning_content
    assert build_streaming_content({}) == ""


def test_build_streaming_content_renders_spinner_during_initial_waiting_state() -> None:
    content = build_streaming_content(
        {
            "heading": "Generating reply",
            "status": "Waiting for streamed output",
            "spinner_frame": 0,
        }
    )

    assert content == "● • • Generating reply"


def test_build_streaming_content_uses_connection_status_when_only_hidden_status_items_exist() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "status",
                    "state": "running",
                    "title": "Starting Codex",
                }
            ],
            "spinner_frame": 1,
        }
    )

    assert content == "• ● • Starting Codex"


def test_build_streaming_content_returns_answer_only_after_answer_starts() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Explored codebase",
                    "mode": "exploration",
                    "command": "rg -n Voyager",
                    "exit_code": 0,
                    "output_preview": "Gemini Voyager\nGemini Voyager 2",
                }
            ],
            "started_at": "2026-03-11T00:00:00+00:00",
            "partial_text": "找到结果，准备整理。",
        }
    )

    assert "🔵 Explored" in content
    assert "Search Voyager" in content
    assert "=====output=====" in content
    assert "Gemini&nbsp;Voyager" in content
    assert "---" in content
    assert content.endswith("找到结果，准备整理。")
    assert content.index("🔵 Explored") < content.index("---")


def test_build_streaming_content_interleaves_summary_blocks_with_history_items() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Explored codebase",
                    "mode": "exploration",
                    "command": "rg -n Voyager",
                    "exit_code": 0,
                    "output_preview": "Gemini Voyager",
                },
                {"type": "summary", "state": "completed", "text": "第一段总结"},
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Ran shell command",
                    "mode": "command",
                    "command": "sed -n '1,10p' src/openrelay/runtime/live.py",
                    "exit_code": 0,
                    "output_preview": "from __future__ import annotations",
                },
                {"type": "summary", "state": "running", "text": "第二段总结"},
            ]
        }
    )

    assert "🔵 Explored" in content
    assert "---\n\n第一段总结" in content
    assert "🟢 Ran" in content
    assert "<font color='blue'>sed</font>" in content
    assert "<font color='purple'>-n</font>" in content
    assert "<font color='wathet'>src/openrelay/runtime/live.py</font>" in content
    assert "=====output=====" in content
    assert "---\n\n第二段总结" in content


def test_build_streaming_content_keeps_summary_and_partial_text_in_one_transcript() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "summary",
                    "state": "completed",
                    "text": "已经确认 reply_card 是入口。",
                },
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Ran shell command",
                    "mode": "command",
                    "command": "git status --short",
                    "exit_code": 0,
                    "output_preview": "M docs/architecture.md",
                },
            ],
            "partial_text": "下一步检查 streaming session 的更新路径。",
        }
    )

    assert "---\n\n已经确认 reply_card 是入口。" in content
    assert "🟢 Ran" in content
    assert "<font color='blue'>git</font>" in content
    assert "<font color='purple'>--short</font>" in content
    assert "<font color='wathet'>docs/architecture.md</font>" in content
    assert content.endswith("---\n\n下一步检查 streaming session 的更新路径。")


def test_build_streaming_content_keeps_history_summary_separate_from_partial_answer() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {"type": "summary", "state": "completed", "text": "上一段总结"},
            ],
            "partial_text": "# Final Answer\n新的正文",
        }
    )

    assert content.startswith("---\n\n上一段总结")
    assert content.endswith("---\n\n#### Final Answer\n新的正文")


def test_build_streaming_content_renders_commentary_inline_during_streaming() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "web_search",
                    "state": "running",
                    "title": "Searching web",
                    "search_id": "search_1",
                    "query": "openharness skill",
                    "queries": ["openharness skill"],
                },
                {
                    "type": "commentary",
                    "state": "running",
                    "title": "进展",
                    "commentary_id": "c1",
                    "text": "我用 using-openharness 做了最小入口检查。",
                },
            ]
        }
    )

    assert "Searching" in content
    assert "---" in content
    assert "• 我用 using-openharness 做了最小入口检查。" in content
    assert "进展" not in content
    assert content.index("Searching") < content.index("• 我用 using-openharness 做了最小入口检查。")



def test_build_streaming_content_marks_failed_command_with_red_dot() -> None:
    content = build_streaming_content(
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
                }
            ],
            "started_at": "2026-03-11T00:00:00+00:00",
        }
    )

    assert "🔴 Ran" in content
    assert "<font color='blue'>pytest</font>" in content
    assert "exit 1" in content
    assert "=====output=====" in content
    assert "<font color='orange'>1</font>&nbsp;<font color='red'>failed</font>" in content
    assert "<font color='red'>AssertionError</font>" in content


def test_build_streaming_content_highlights_diff_output_with_codex_colors() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Ran shell command",
                    "mode": "command",
                    "command": "git diff -- src/openrelay/feishu/reply_card.py",
                    "exit_code": 0,
                    "output_preview": "--- a/src/openrelay/feishu/reply_card.py\n+++ b/src/openrelay/feishu/reply_card.py\n@@ -1,2 +1,2 @@\n-old line\n+new line",
                }
            ]
        }
    )

    assert "<font color='grey'>---&nbsp;a/src/openrelay/feishu/reply_card.py</font>" in content
    assert "<font color='grey'>+++&nbsp;b/src/openrelay/feishu/reply_card.py</font>" in content
    assert "<font color='grey'>@@&nbsp;-1,2&nbsp;+1,2&nbsp;@@</font>" in content
    assert "<text_tag color='red'>-</text_tag>" in content
    assert "<font color='red'>old</font>" in content
    assert "<font color='red'>&nbsp;</font>" in content
    assert "<font color='red'>line</font>" in content
    assert "<text_tag color='green'>+</text_tag>" in content
    assert "<font color='green'>new</font>" in content
    assert "<font color='green'>line</font>" in content


def test_build_streaming_content_renders_full_diff_without_truncating_changed_lines() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "file_change",
                    "state": "completed",
                    "title": "Updated files",
                    "changes": [
                        {"path": "docs/edit-update-demo.txt", "kind": {"type": "add"}},
                    ],
                    "detail": (
                        "diff --git a/docs/edit-update-demo.txt b/docs/edit-update-demo.txt\n"
                        "new file mode 100644\n"
                        "index 0000000..827d0d8\n"
                        "--- /dev/null\n"
                        "+++ b/docs/edit-update-demo.txt\n"
                        "@@ -0,0 +1,3 @@\n"
                        "+hello\n"
                        "+world\n"
                        "+done\n"
                    ),
                }
            ]
        }
    )

    assert "<font color='wathet'>diff&nbsp;--git&nbsp;a/docs/edit-update-demo.txt&nbsp;b/docs/edit-update-demo.txt</font>" in content
    assert "<text_tag color='green'>+</text_tag><font color='green'>hello</font>" in content
    assert "<text_tag color='green'>+</text_tag><font color='green'>world</font>" in content
    assert "...&nbsp;+3&nbsp;lines" not in content


def test_build_streaming_content_syntax_highlights_diff_lines_by_file_type() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "file_change",
                    "state": "completed",
                    "title": "Updated files",
                    "changes": [
                        {"path": "src/demo.py", "kind": {"type": "update"}},
                    ],
                    "detail": (
                        "diff --git a/src/demo.py b/src/demo.py\n"
                        "--- a/src/demo.py\n"
                        "+++ b/src/demo.py\n"
                        "@@ -1 +1 @@\n"
                        "-print('old')\n"
                        "+print('new')\n"
                    ),
                }
            ]
        }
    )

    assert "<text_tag color='red'>-</text_tag>" in content
    assert "<text_tag color='green'>+</text_tag>" in content
    assert "<font color='purple'>print</font>" in content
    assert "<font color='green'>new</font>" in content
    assert ">old</font>" in content


def test_build_streaming_content_preserves_output_indentation_without_code_fence() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Ran shell command",
                    "mode": "command",
                    "command": "python demo.py",
                    "exit_code": 0,
                    "output_preview": "def main():\n    print('hi')",
                }
            ]
        }
    )

    assert "```text" not in content
    assert "=====output=====" in content
    assert "<font color='purple'>def</font>" in content
    assert "<font color='blue'>main</font>" in content
    assert "&nbsp;&nbsp;&nbsp;&nbsp;<font color='purple'>print</font>" in content


def test_build_streaming_content_wraps_long_command_into_pipe_lines() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Ran shell command",
                    "mode": "command",
                    "command": "uv run python scripts/export_schema.py --format json --output docs/schema.json",
                    "exit_code": 0,
                }
            ]
        }
    )

    assert "🟢 Ran" in content
    assert "<font color='blue'>uv</font>" in content
    assert "<font color='wathet'>scripts/export_schema.py</font>" in content
    assert "<font color='purple'>--format</font>" in content


def test_render_command_chunks_wraps_shell_script_argument_without_losing_string_style() -> None:
    chunks = render_command_chunks(
        "/bin/bash -lc \"printf 'Using skill: project-memory, to check whether this repo already has a recorded project summary.\\n' >&2 ...\"",
        target_length=34,
        max_lines=6,
    )

    assert len(chunks) == 5
    assert chunks[0].startswith("<font color='wathet'>/bin/bash</font>")
    assert "<font color='purple'>-lc</font>" in chunks[0]
    assert "<font color='green'>\"printf</font>" in chunks[0]
    assert "<font color='green'>skill:</font>" in chunks[1]
    assert "<font color='green'>project-memory,</font>" in chunks[1]
    assert any("<font color='green'>recorded</font>" in chunk for chunk in chunks)
    assert any("<font color='green'>summary.\\n'</font>" in chunk for chunk in chunks)


def test_build_streaming_content_composes_plain_output_colors() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Ran shell command",
                    "mode": "command",
                    "command": "pytest -q tests/test_feishu_streaming.py",
                    "exit_code": 1,
                    "output_preview": "tests/test_feishu_streaming.py:193: AssertionError",
                }
            ]
        }
    )

    assert "<font color='wathet'>tests/test_feishu_streaming.py</font>" in content
    assert "<font color='orange'>193</font>" in content
    assert "<font color='red'>AssertionError</font>" in content


def test_build_streaming_content_strips_ansi_sequences_from_output() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Ran shell command",
                    "mode": "command",
                    "command": "pytest -q",
                    "exit_code": 1,
                    "output_preview": "\x1b[31mFAILED\x1b[0m tests/test_x.py::test_a - AssertionError",
                }
            ]
        }
    )

    assert "\x1b" not in content
    assert "<font color='red'>FAILED</font>" in content
    assert "<font color='wathet'>tests/test_x.py</font>" in content


def test_build_streaming_content_keeps_url_and_path_colors_separate() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Ran shell command",
                    "mode": "command",
                    "command": "curl https://example.com",
                    "exit_code": 0,
                    "output_preview": "See https://example.com/docs/index.html and ./tmp/out.json",
                }
            ]
        }
    )

    assert "<font color='blue'>https://example.com/docs/index.html</font>" in content
    assert "<font color='wathet'>./tmp/out.json</font>" in content


def test_build_streaming_content_does_not_infer_json_lexer_from_output_target_path() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Ran shell command",
                    "mode": "command",
                    "command": "uv run python scripts/export_schema.py --format json --output docs/schema.json",
                    "exit_code": 0,
                    "output_preview": "File saved to docs/schema.json in 0.12s",
                }
            ]
        }
    )

    assert "<font color='green'>saved</font>" in content
    assert "<font color='wathet'>docs/schema.json</font>" in content
    assert "<font color='orange'>0.12</font>" in content
    assert "<font color='wathet'>docs/schema.json</font>" in content


def test_build_streaming_content_wraps_command_by_target_character_width() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Ran shell command",
                    "mode": "command",
                    "command": '/bin/bash -lc "sed -n \'150,260p\' src/openrelay/feishu/reply_card.py"',
                    "exit_code": 0,
                }
            ]
        }
    )

    assert "<font color='wathet'>/bin/bash</font>" in content
    assert "<font color='purple'>-lc</font>" in content
    assert '<font color=\'green\'>"sed</font>' in content
    assert '<font color=\'green\'>src/openrelay/feishu/reply_card.py"</font>' in content


def test_build_streaming_content_keeps_tree_prefix_outside_command_highlight() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Ran shell command",
                    "mode": "command",
                    "command": "/bin/bash -lc \"printf 'Using skill: project-memory, to check whether this repo already has a recorded project summary.\\n' >&2 ...\"",
                    "exit_code": 0,
                }
            ]
        }
    )

    assert "\n│ <font color='wathet'>/bin/bash</font>" in content
    assert "\n│ <font color='green'>skill:</font>" in content
    assert "\n└ <font color='green'>recorded</font>" in content
    assert "<font color='green'>summary.\\n'</font>" in content
    assert "<font color='grey'>│</font>" not in content
    assert "<font color='grey'>└</font>" not in content


def test_build_streaming_content_keeps_tree_prefix_when_command_contains_literal_newline() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "command",
                    "state": "completed",
                    "title": "Ran shell command",
                    "mode": "command",
                    "command": "/bin/bash -lc \"printf '%s\n' '--- tool-demo-new.txt ---' && nl -ba tool-demo-new.txt\"",
                    "exit_code": 0,
                }
            ]
        }
    )

    assert "\n│ <font color='wathet'>/bin/bash</font>" in content
    assert "\n│ <font color='green'>'</font><font color='green'>&nbsp;</font><font color='green'>'---</font>" in content
    assert "\n└ <font color='green'>nl</font>" in content


def test_build_streaming_content_renders_web_search_as_blue_exploration() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "web_search",
                    "state": "completed",
                    "title": "Searched web",
                    "query": "March 11 2026 AI news Reuters generative AI",
                    "queries": [
                        "March 11 2026 AI news Reuters generative AI",
                        "site:techcrunch.com AI March 11 2026",
                    ],
                }
            ]
        }
    )

    assert "🔵 Searched" in content
    assert "Search March 11 2026 AI news Reuters generative AI" in content
    assert "Search site:techcrunch.com AI March 11 2026" in content


def test_build_streaming_content_renders_plan_with_static_purple_bullets_and_strikethrough() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "plan",
                    "state": "running",
                    "title": "Plan",
                    "steps": [
                        {"step": "Inspect runtime", "status": "completed"},
                        {"step": "Adjust Feishu rendering", "status": "in_progress"},
                        {"step": "Verify snapshot output", "status": "pending"},
                    ],
                }
            ]
        }
    )

    assert "🟣 Plan" in content
    assert "🟣 Plan  \n│  \n● ~~Inspect runtime~~" in content
    assert "● ~~Inspect runtime~~" in content
    assert "◉ Adjust Feishu rendering" in content
    assert "○ Verify snapshot output" in content


def test_build_streaming_content_renders_updated_files_with_section_separator() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "file_change",
                    "state": "completed",
                    "title": "Updated files",
                    "changes": [
                        {"path": "src/openrelay/feishu/reply_card.py", "kind": {"type": "update"}},
                        {"path": "tests/test_feishu_streaming.py", "kind": {"type": "update"}},
                    ],
                    "detail": "--- a/src/openrelay/feishu/reply_card.py\n+++ b/src/openrelay/feishu/reply_card.py\n@@ -1 +1 @@\n-old line\n+new line",
                }
            ]
        }
    )

    assert "🟠 Updated files" in content
    assert "🟠 Updated files  \n│  \n<text_tag color='orange'>Edit</text_tag> `src/openrelay/feishu/reply_card.py`" in content
    assert "<text_tag color='orange'>Edit</text_tag> `tests/test_feishu_streaming.py`" in content
    assert "=====output=====" in content
    assert "<font color='grey'>---&nbsp;a/src/openrelay/feishu/reply_card.py</font>" in content
    assert "<text_tag color='red'>-</text_tag><font color='red'>old</font><font color='red'>&nbsp;</font><font color='red'>line</font>" in content
    assert "<text_tag color='green'>+</text_tag><font color='green'>new</font><font color='green'>&nbsp;</font><font color='green'>line</font>" in content


def test_build_streaming_content_renders_turn_diff_fallback_for_file_change() -> None:
    presenter = LiveTurnPresenter()
    snapshot = presenter.build_snapshot(
        LiveTurnViewModel(
            backend="codex",
            session_id="relay_1",
            native_session_id="thread_1",
            turn_id="turn_1",
            status="running",
            latest_diff="--- a/tool-demo-edit.txt\n+++ b/tool-demo-edit.txt\n@@ -1,2 +1,2 @@\n-状态: 旧值\n+状态: 已更新",
            tools=(
                ToolState(
                    tool_id="fc_1",
                    kind="file_change",
                    title="File changes",
                    status="completed",
                    preview="tool-demo-edit.txt",
                    detail="",
                    provider_payload={
                        "changes": [
                            {
                                "path": "/home/Shaokun.Tang/Projects/tool-demo-edit.txt",
                                "kind": {"type": "update"},
                            }
                        ]
                    },
                ),
            ),
        )
    )

    content = build_streaming_content(snapshot)

    assert "🟠 Updated files" in content
    assert "<text_tag color='orange'>Edit</text_tag> `/home/Shaokun.Tang/Projects/tool-demo-edit.txt`" in content
    assert "=====output=====" in content
    assert "<font color='grey'>---&nbsp;a/tool-demo-edit.txt</font>" in content
    assert "<font color='grey'>+++&nbsp;b/tool-demo-edit.txt</font>" in content
    assert "<text_tag color='red'>-</text_tag><font color='red'>状态:&nbsp;旧值</font>" in content
    assert "<text_tag color='green'>+</text_tag><font color='green'>状态:&nbsp;已更新</font>" in content


def test_build_streaming_content_renders_unexpected_backend_event_payload() -> None:
    content = build_streaming_content(
        {
            "history_items": [
                {
                    "type": "backend_event",
                    "state": "completed",
                    "title": "Unexpected backend event: item/unknownEvent",
                    "detail": "Unexpected backend event: item/unknownEvent\n\n{\n  \"method\": \"item/unknownEvent\",\n  \"params\": {\n    \"foo\": \"bar\"\n  }\n}",
                }
            ]
        }
    )

    assert "Unexpected backend event: item/unknownEvent" in content
    assert '"method": "item/unknownEvent"' in content
    assert '"foo": "bar"' in content
