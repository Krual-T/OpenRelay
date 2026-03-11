from openrelay.runtime_live import build_reply_card


def test_build_reply_card_uses_semantic_header_template() -> None:
    success_card = build_reply_card("done", "openrelay 回复")
    failed_card = build_reply_card("处理失败：boom", "openrelay 回复")
    cancelled_card = build_reply_card("已停止当前回复。", "openrelay 回复")

    assert success_card["header"]["template"] == "green"
    assert failed_card["header"]["template"] == "red"
    assert cancelled_card["header"]["template"] == "grey"


def test_build_reply_card_adds_collapsible_reasoning_panel() -> None:
    card = build_reply_card("done", "openrelay 回复", reasoning_text="先读代码", reasoning_elapsed_ms=12000)

    assert any(element.get("tag") == "collapsible_panel" for element in card["elements"] if isinstance(element, dict))
    assert any(
        element.get("tag") == "markdown" and element.get("content") == "done"
        for element in card["elements"]
        if isinstance(element, dict)
    )
