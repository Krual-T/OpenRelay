from openrelay.runtime_live import build_reply_card


def test_build_reply_card_uses_semantic_status_heading() -> None:
    success_card = build_reply_card("done", "openrelay 回复")
    failed_card = build_reply_card("处理失败：boom", "openrelay 回复")
    cancelled_card = build_reply_card("已停止当前回复。", "openrelay 回复")

    assert success_card["schema"] == "2.0"
    assert success_card["config"]["streaming_mode"] is False
    assert "`已完成`" in success_card["body"]["elements"][0]["content"]
    assert "`失败`" in failed_card["body"]["elements"][0]["content"]
    assert "`已取消`" in cancelled_card["body"]["elements"][0]["content"]


def test_build_reply_card_adds_collapsible_reasoning_panel() -> None:
    card = build_reply_card("done", "openrelay 回复", reasoning_text="先读代码", reasoning_elapsed_ms=12000)

    assert any(element.get("tag") == "collapsible_panel" for element in card["body"]["elements"] if isinstance(element, dict))
    assert any(
        element.get("tag") == "markdown" and element.get("content") == "done"
        for element in card["body"]["elements"]
        if isinstance(element, dict)
    )
