import pytest

import openrelay.feishu.streaming as streaming_card_module
from openrelay.feishu.reply_card import build_streaming_card_signature
from openrelay.feishu.reply_card import build_complete_card
from openrelay.feishu import (
    DEFAULT_THINKING_TEXT,
    FeishuStreamingSession,
    STREAMING_ELEMENT_ID,
    build_streaming_card_json,
    build_streaming_content,
)


def test_build_streaming_card_json_uses_single_streaming_element() -> None:
    card = build_streaming_card_json()

    assert card["schema"] == "2.0"
    assert card["config"]["streaming_mode"] is True
    assert card["config"]["summary"]["content"] == DEFAULT_THINKING_TEXT
    assert card["body"]["elements"][0]["element_id"] == STREAMING_ELEMENT_ID
    assert card["body"]["elements"][0]["content"] == ""
    assert card["body"]["elements"][1]["element_id"] == "loading_icon"
    assert card["body"]["elements"][1]["icon"]["img_key"].startswith("img_")


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
    assert card["config"]["summary"]["content"] == DEFAULT_THINKING_TEXT
    assert card["body"]["elements"][0]["element_id"] == STREAMING_ELEMENT_ID
    assert "🔵 **Explored**" in card["body"]["elements"][0]["content"]
    assert "#### Answer\n找到结果。" in card["body"]["elements"][0]["content"]
    assert card["body"]["elements"][1]["element_id"] == "loading_icon"


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
    assert "• **Thinking**" in reasoning_content
    assert "- 先看代码" in reasoning_content
    assert build_streaming_content({}) == ""


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

    assert "🔵 **Explored**" in content
    assert "---" in content
    assert content.endswith("找到结果，准备整理。")
    assert content.index("🔵 **Explored**") < content.index("---")


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

    assert "🔵 **Explored**" in content
    assert "---\n\n第一段总结" in content
    assert "• **Ran**" in content
    assert "- `sed -n '1,10p' src/openrelay/runtime/live.py`" in content
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
    assert "• **Ran**" in content
    assert "- `git status --short`" in content
    assert content.endswith("---\n\n下一步检查 streaming session 的更新路径。")


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

    assert "🔴 **Ran**" in content
    assert "- `pytest`" in content
    assert "- exit 1" in content
    assert "- `1 failed`" in content
    assert "- `AssertionError`" in content


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

    assert "🔵 **Searched**" in content
    assert "- Search March 11 2026 AI news Reuters generative AI" in content
    assert "- Search site:techcrunch.com AI March 11 2026" in content


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

    assert "🟣 **Plan**" in content
    assert "- 🟣 ~~`completed` Inspect runtime~~" in content
    assert "- 🟣 `in_progress` Adjust Feishu rendering" in content
    assert "- 🟣 `pending` Verify snapshot output" in content


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


@pytest.mark.asyncio
async def test_streaming_session_switches_to_answer_card_when_answer_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FeishuStreamingSession(object())
    session.state = {
        "card_id": "c1",
        "sequence": 1,
        "current_content": "",
        "card_signature": ("plain", ""),
    }
    calls: list[tuple[str, object]] = []

    async def fake_update_card_json(card_json: dict[str, object]) -> None:
        calls.append(("update_json", card_json))

    async def fake_update_card_content(text: str) -> None:
        calls.append(("update_content", text))

    monkeypatch.setattr(session, "update_card_json", fake_update_card_json)
    monkeypatch.setattr(session, "update_card_content", fake_update_card_content)

    await session.update(
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

    assert len(calls) == 1
    assert calls[0][0] == "update_content"
    assert "🔵 **Explored**" in str(calls[0][1])
    assert "#### Answer\n找到结果。" in str(calls[0][1])
    assert session.state["current_content"].endswith("#### Answer\n找到结果。")
    assert session.state["card_signature"][0] == "plain"


@pytest.mark.asyncio
async def test_streaming_session_updates_answer_content_after_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    live_state = {
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
        "partial_text": "# Answer\n第一段",
    }
    session = FeishuStreamingSession(object())
    first_content = build_streaming_content(live_state)
    session.state = {
        "card_id": "c1",
        "sequence": 2,
        "current_content": first_content,
        "card_signature": build_streaming_card_signature(live_state),
    }
    calls: list[tuple[str, object]] = []

    async def fake_update_card_json(card_json: dict[str, object]) -> None:
        calls.append(("update_json", card_json))

    async def fake_update_card_content(text: str) -> None:
        calls.append(("update_content", text))

    monkeypatch.setattr(session, "update_card_json", fake_update_card_json)
    monkeypatch.setattr(session, "update_card_content", fake_update_card_content)

    live_state["partial_text"] = "# Answer\n第二段"
    await session.update(live_state)

    assert len(calls) == 1
    assert calls[0][0] == "update_json"
    assert session.state["current_content"].endswith("#### Answer\n第二段")
    assert session.state["card_signature"][0] == "plain"


@pytest.mark.asyncio
async def test_streaming_session_throttles_updates_to_short_cardkit_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FeishuStreamingSession(object())
    session.state = {
        "card_id": "c1",
        "sequence": 1,
        "current_content": DEFAULT_THINKING_TEXT,
        "card_signature": ("plain", ""),
    }
    applied_contents: list[str] = []
    applied_cards: list[dict[str, object]] = []

    async def fake_update_card_content(text: str) -> None:
        applied_contents.append(text)
        session.state["current_content"] = f"{session.state['current_content']}{text}"
        session.last_update_time = clock["now"] * 1000

    async def fake_update_card_json(card_json: dict[str, object]) -> None:
        applied_cards.append(card_json)
        session.state["card_signature"] = build_streaming_card_signature({"partial_text": session.pending_content or "第一段"})
        session.state["current_content"] = card_json["body"]["elements"][0]["content"]
        session.last_update_time = clock["now"] * 1000

    clock = {"now": 10.0}
    monkeypatch.setattr(streaming_card_module.time, "time", lambda: clock["now"])
    monkeypatch.setattr(session, "update_card_content", fake_update_card_content)
    monkeypatch.setattr(session, "update_card_json", fake_update_card_json)

    await session.update({"partial_text": "第一段"})
    assert len(applied_cards) == 1
    assert applied_contents == []
    assert session.state["current_content"] == "---\n\n第一段"
    assert session.pending_content == ""

    clock["now"] = 10.05
    await session.update({"partial_text": "第二段"})
    assert applied_contents == []
    assert len(applied_cards) == 2
    assert session.pending_content == ""

    clock["now"] = 10.2
    await session.update({"partial_text": "第二段"})
    assert applied_contents == []
    assert session.pending_content == ""


@pytest.mark.asyncio
async def test_streaming_session_close_disables_streaming_before_final_card_update(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FeishuStreamingSession(object())
    session.state = {
        "card_id": "c1",
        "sequence": 1,
        "current_content": DEFAULT_THINKING_TEXT,
    }
    calls: list[tuple[str, object]] = []

    async def fake_set_streaming_mode(enabled: bool) -> None:
        calls.append(("settings", enabled))

    async def fake_update_card_json(card_json: dict[str, object]) -> None:
        calls.append(("update", card_json))

    monkeypatch.setattr(session, "set_streaming_mode", fake_set_streaming_mode)
    monkeypatch.setattr(session, "update_card_json", fake_update_card_json)

    await session.close({"schema": "2.0", "config": {"streaming_mode": False}, "body": {"elements": []}})

    assert session.closed is True
    assert calls == [
        ("settings", False),
        ("update", {"schema": "2.0", "config": {"streaming_mode": False}, "body": {"elements": []}}),
    ]


@pytest.mark.asyncio
async def test_streaming_session_freezes_before_platform_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FeishuStreamingSession(object())
    session.state = {
        "card_id": "c1",
        "sequence": 1,
        "current_content": "---\n第一段",
        "card_signature": ("plain", ""),
    }
    session.started_at_ms = 1_000.0
    session.card_streaming_window_seconds = 540.0
    calls: list[tuple[str, object]] = []

    async def fake_set_streaming_mode(enabled: bool) -> None:
        calls.append(("settings", enabled))

    async def fake_update_card_json(card_json: dict[str, object]) -> None:
        calls.append(("update", card_json))

    monkeypatch.setattr(streaming_card_module.time, "time", lambda: 541.0)
    monkeypatch.setattr(session, "set_streaming_mode", fake_set_streaming_mode)
    monkeypatch.setattr(session, "update_card_json", fake_update_card_json)

    await session.update({"partial_text": "第二段"})

    assert session.is_active() is False
    assert calls[0] == ("settings", False)
    assert calls[1][0] == "update"
    assert "流式显示已自动暂停" in str(calls[1][1])
    assert "第二段" in str(calls[1][1])


@pytest.mark.asyncio
async def test_streaming_session_close_updates_final_card_after_freeze(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FeishuStreamingSession(object())
    session.state = {
        "card_id": "c1",
        "sequence": 1,
        "current_content": DEFAULT_THINKING_TEXT,
    }
    session.streaming_mode_enabled = False
    calls: list[tuple[str, object]] = []

    async def fake_set_streaming_mode(enabled: bool) -> None:
        calls.append(("settings", enabled))

    async def fake_update_card_json(card_json: dict[str, object]) -> None:
        calls.append(("update", card_json))

    monkeypatch.setattr(session, "set_streaming_mode", fake_set_streaming_mode)
    monkeypatch.setattr(session, "update_card_json", fake_update_card_json)

    await session.close({"schema": "2.0", "config": {"streaming_mode": False}, "body": {"elements": []}})

    assert calls == [
        ("update", {"schema": "2.0", "config": {"streaming_mode": False}, "body": {"elements": []}}),
    ]


def test_build_complete_card_prefers_transcript_markdown() -> None:
    card = build_complete_card(
        "最终答案",
        transcript_markdown="• **Ran** `pytest`\n\n---\n\n最终答案",
        summary_text="最终答案",
    )

    assert card["body"]["elements"] == [{"tag": "markdown", "content": "• **Ran** `pytest`\n\n---\n\n最终答案"}]
    assert card["config"]["summary"]["content"] == "最终答案"


@pytest.mark.asyncio
async def test_streaming_session_appends_delta_when_transcript_is_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FeishuStreamingSession(object())
    initial_state = {
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
        "partial_text": "# Answer\n第一段",
    }
    current_content = build_streaming_content(initial_state)
    session.state = {
        "card_id": "c1",
        "sequence": 1,
        "current_content": current_content,
        "card_signature": ("plain", ""),
    }
    calls: list[tuple[str, object]] = []

    async def fake_update_card_json(card_json: dict[str, object]) -> None:
        calls.append(("update_json", card_json))

    async def fake_update_card_content(text: str) -> None:
        calls.append(("update_content", text))

    monkeypatch.setattr(session, "update_card_json", fake_update_card_json)
    monkeypatch.setattr(session, "update_card_content", fake_update_card_content)

    await session.update(
        {
            "history_items": initial_state["history_items"],
            "partial_text": "# Answer\n第一段\n第二段",
        }
    )

    assert calls == [("update_content", "\n第二段")]


@pytest.mark.asyncio
async def test_streaming_session_rebuilds_card_when_transcript_rewrites_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FeishuStreamingSession(object())
    live_state = {
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
        "partial_text": "# Answer\n第一段",
    }
    session.state = {
        "card_id": "c1",
        "sequence": 1,
        "current_content": build_streaming_content(live_state),
        "card_signature": ("plain", ""),
    }
    calls: list[tuple[str, object]] = []

    async def fake_update_card_json(card_json: dict[str, object]) -> None:
        calls.append(("update_json", card_json))

    async def fake_update_card_content(text: str) -> None:
        calls.append(("update_content", text))

    monkeypatch.setattr(session, "update_card_json", fake_update_card_json)
    monkeypatch.setattr(session, "update_card_content", fake_update_card_content)

    rewritten_state = dict(live_state)
    rewritten_state["history_items"] = [
        dict(live_state["history_items"][0]) | {"state": "failed", "title": "Ran shell command", "mode": "command", "exit_code": 1}
    ]
    await session.update(rewritten_state)

    assert len(calls) == 1
    assert calls[0][0] == "update_json"
