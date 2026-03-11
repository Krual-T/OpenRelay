import pytest

import openrelay.streaming_card as streaming_card_module
from openrelay.streaming_card import (
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


def test_build_streaming_content_prefers_partial_text_then_reasoning() -> None:
    assert build_streaming_content({"partial_text": "# Title\ncontent"}) == "#### Title\ncontent"
    assert build_streaming_content({"partial_text": "<think>先看代码</think>\n答案"}) == "答案"
    assert build_streaming_content({"reasoning_text": "先看代码"}) == "💭 **Thinking...**\n\n先看代码"
    assert build_streaming_content({}) == ""


@pytest.mark.asyncio
async def test_streaming_session_throttles_updates_to_short_cardkit_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FeishuStreamingSession(object())
    session.state = {
        "current_content": DEFAULT_THINKING_TEXT,
    }
    applied_contents: list[str] = []

    async def fake_update_card_content(text: str) -> None:
        applied_contents.append(text)
        session.state["current_content"] = text
        session.last_update_time = clock["now"] * 1000

    clock = {"now": 10.0}
    monkeypatch.setattr(streaming_card_module.time, "time", lambda: clock["now"])
    monkeypatch.setattr(session, "update_card_content", fake_update_card_content)

    await session.update({"partial_text": "第一段"})
    assert applied_contents == ["第一段"]
    assert session.pending_content == ""

    clock["now"] = 10.05
    await session.update({"partial_text": "第二段"})
    assert applied_contents == ["第一段"]
    assert session.pending_content == "第二段"

    clock["now"] = 10.2
    await session.update({"partial_text": "第二段"})
    assert applied_contents == ["第一段", "第二段"]
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
