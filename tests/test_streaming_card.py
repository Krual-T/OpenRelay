from openrelay.streaming_card import build_card_json, build_final_sections


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
