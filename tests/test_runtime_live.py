from openrelay.runtime_live import build_reply_card


def test_build_reply_card_uses_semantic_header_template() -> None:
    success_card = build_reply_card("done", "openrelay 回复")
    failed_card = build_reply_card("处理失败：boom", "openrelay 回复")
    cancelled_card = build_reply_card("已停止当前回复。", "openrelay 回复")

    assert success_card["header"]["template"] == "green"
    assert failed_card["header"]["template"] == "red"
    assert cancelled_card["header"]["template"] == "grey"


def test_build_reply_card_adds_visual_sections() -> None:
    card = build_reply_card("done", "openrelay 回复")

    assert any("```text" in element.get("text", {}).get("content", "") for element in card["elements"] if isinstance(element, dict))
    assert any(element.get("tag") == "hr" for element in card["elements"])
    assert any("回复内容" in element.get("text", {}).get("content", "") for element in card["elements"] if isinstance(element, dict))
