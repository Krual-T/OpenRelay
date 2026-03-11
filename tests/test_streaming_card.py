import pytest

import openrelay.streaming_card as streaming_card_module
from openrelay.streaming_card import FeishuStreamingSession, build_card_json, build_final_sections, sections_signature


def test_build_card_json_keeps_section_order() -> None:
    card = build_card_json({"header": "h", "details": "d", "body": "b"})

    assert card["schema"] == "2.0"
    assert [element["element_id"] for element in card["body"]["elements"]] == ["header", "details", "body"]


def test_build_final_sections_uses_semantic_status_heading() -> None:
    failed = build_final_sections("处理失败：boom")
    cancelled = build_final_sections("已停止当前回复。")

    assert "`失败`" in failed["header"]
    assert failed["body"] == "处理失败：boom"
    assert "`已取消`" in cancelled["header"]


@pytest.mark.asyncio
async def test_streaming_session_throttles_updates_to_one_second(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FeishuStreamingSession(object())
    session.state = {
        "current_sections": {"header": "", "details": "", "body": ""},
        "current_signature": sections_signature({"header": "", "details": "", "body": ""}),
    }
    applied_sections: list[dict[str, str]] = []

    async def fake_apply_sections(sections: dict[str, str], animate_body: bool = True) -> None:
        applied_sections.append(sections)
        session.state["current_sections"] = sections
        session.state["current_signature"] = sections_signature(sections)

    clock = {"now": 10.0}
    monkeypatch.setattr(streaming_card_module.time, "time", lambda: clock["now"])
    monkeypatch.setattr(session, "apply_sections", fake_apply_sections)

    await session.update({"heading": "正在生成回复", "status": "第一段"})
    assert len(applied_sections) == 1
    assert session.pending_sections is None

    clock["now"] = 10.5
    await session.update({"heading": "正在生成回复", "status": "第二段"})
    assert len(applied_sections) == 1
    assert session.pending_sections is not None

    clock["now"] = 11.1
    await session.update({"heading": "正在生成回复", "status": "第二段"})
    assert len(applied_sections) == 2
    assert session.pending_sections is None
