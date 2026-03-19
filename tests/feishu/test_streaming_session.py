from tests.support.feishu_streaming import (
    DEFAULT_THINKING_TEXT,
    FeishuStreamingSession,
    _RecordingMessenger,
    build_streaming_card_json,
    build_streaming_card_signature,
    build_streaming_content,
    pytest,
    streaming_card_module,
)


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
    assert calls[0][0] == "update_json"
    assert "🔵 Explored" in str(calls[0][1])
    assert "#### Answer\n找到结果。" in str(calls[0][1]["body"]["elements"][0]["content"])
    assert session.state["current_content"].endswith("#### Answer\n找到结果。")
    assert session.state["card_signature"] == build_streaming_card_signature(
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
            ]
        }
    )

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
        session.state["current_content"] = text
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

@pytest.mark.asyncio
async def test_streaming_session_update_card_content_keeps_nbsp_entities(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    messenger = _RecordingMessenger()
    session = FeishuStreamingSession(messenger)
    session.state = {
        "card_id": "c1",
        "sequence": 1,
        "current_content": "",
        "card_signature": ("plain", ""),
    }

    await session.update_card_content("=====output=====\n&nbsp;&nbsp;&nbsp;&nbsp;return&nbsp;raw")

    request = messenger.client.cardkit.v1.card_element.calls[0]
    assert request.request_body.content == "=====output=====\n&nbsp;&nbsp;&nbsp;&nbsp;return&nbsp;raw"
    assert any("streaming update card content" in record.getMessage() for record in caplog.records)

@pytest.mark.asyncio
async def test_streaming_session_update_card_json_keeps_nbsp_entities(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    messenger = _RecordingMessenger()
    session = FeishuStreamingSession(messenger)
    session.state = {
        "card_id": "c1",
        "sequence": 1,
        "current_content": "",
        "card_signature": ("plain", ""),
    }
    card_json = build_streaming_card_json(
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

    await session.update_card_json(card_json)

    request = messenger.client.cardkit.v1.card.update_calls[0]
    data = request.request_body.card.data
    assert "&nbsp;&nbsp;&nbsp;&nbsp;" in data
    assert "\\u00a0" not in data
    assert any("streaming update card json" in record.getMessage() for record in caplog.records)

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
        "card_signature": build_streaming_card_signature(initial_state),
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

    assert calls == [("update_content", build_streaming_content(
        {
            "history_items": initial_state["history_items"],
            "partial_text": "# Answer\n第一段\n第二段",
        }
    ))]

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
        "card_signature": build_streaming_card_signature(live_state),
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

@pytest.mark.asyncio
async def test_streaming_session_rebuilds_card_when_plan_changes_even_if_content_appends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FeishuStreamingSession(object())
    initial_state = {
        "history_items": [
            {
                "type": "command",
                "state": "completed",
                "title": "Ran shell command",
                "mode": "command",
                "command": "git diff -- src/openrelay/feishu/reply_card.py",
                "exit_code": 0,
                "output_preview": "+new line",
            }
        ],
        "partial_text": "第一段",
    }
    session.state = {
        "card_id": "c1",
        "sequence": 1,
        "current_content": build_streaming_content(initial_state),
        "card_signature": build_streaming_card_signature(initial_state),
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
                *initial_state["history_items"],
                {
                    "type": "plan",
                    "state": "running",
                    "title": "Plan",
                    "steps": [{"step": "Adjust Feishu rendering", "status": "in_progress"}],
                },
            ],
            "partial_text": "第一段\n第二段",
        }
    )

    assert len(calls) == 1
    assert calls[0][0] == "update_json"
