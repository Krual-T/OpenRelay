from openrelay.presentation.session import build_backend_session_list_card, build_session_list_card


def extract_commands(card: dict) -> list[str]:
    commands: list[str] = []
    for element in card.get("elements", []):
        if element.get("tag") != "action":
            continue
        for action in element.get("actions", []):
            value = action.get("value") if isinstance(action, dict) else None
            if isinstance(value, dict) and value.get("command"):
                commands.append(str(value["command"]))
    return commands


def test_session_list_card_contains_pagination_and_sort_actions() -> None:
    card = build_session_list_card(
        {
            "current_title": "current",
            "current_session_id": "s_current",
            "page": 2,
            "sort_mode": "updated-desc",
            "has_previous": True,
            "has_next": True,
            "action_context": {"sessionKey": "p2p:oc_1", "rootId": "root_1"},
            "sessions": [
                {"index": 6, "session_id": "s_6", "resume_token": "s_6", "active": False, "title": "session-6", "meta": "本地", "preview": "preview"},
            ],
        }
    )

    commands = extract_commands(card)
    assert "/resume --page 1 --sort updated-desc" in commands
    assert "/resume --page 3 --sort updated-desc" in commands
    assert "/resume --page 1 --sort active-first" in commands
    assert "/resume s_6 --page 2 --sort updated-desc" in commands


def test_backend_session_list_card_uses_markdown_blocks_without_quote_footer_buttons() -> None:
    card = build_backend_session_list_card(
        {
            "page": 1,
            "known_page_count": 1,
            "backend_name": "codex",
            "action_context": {"sessionKey": "p2p:oc_1", "rootId": "root_1"},
            "sessions": [
                {"index": 1, "session_id": "thread_1", "active": True, "title": "task 1", "meta": "2026-03-16 18:00:00 · status=idle"},
            ],
        }
    )

    assert card["header"]["title"]["content"] == "Relay codex thread histories"
    assert "运行时会话" not in str(card)
    assert "预览" not in str(card)
    assert card["elements"][0]["text"]["content"] == "**1. task 1** · 当前\n2026-03-16 18:00:00 · status=idle\n`thread_1`"
    assert "/resume latest" not in extract_commands(card)
    assert "/panel" not in extract_commands(card)
    assert "/help" not in extract_commands(card)


def test_backend_session_list_card_renders_page_number_strip() -> None:
    card = build_backend_session_list_card(
        {
            "page": 3,
            "known_page_count": 5,
            "has_previous": True,
            "has_next": True,
            "backend_name": "codex",
            "action_context": {"sessionKey": "p2p:oc_1", "rootId": "root_1"},
            "sessions": [
                {"index": 7, "session_id": "thread_7", "active": False, "title": "task 7", "meta": "2026-03-16 18:00:00 · status=idle"},
            ],
        }
    )

    commands = extract_commands(card)
    assert commands[-7:] == [
        "/resume",
        "/resume --page 2",
        "/resume --page 3",
        "/resume --page 4",
        "/resume --page 5",
        "/resume --page 2",
        "/resume --page 4",
    ]

    pagination_rows = [element["actions"] for element in card["elements"] if element.get("tag") == "action"][-2:]
    assert [[action["text"]["content"] for action in row] for row in pagination_rows] == [
        ["1", "2", "3", "4", "5"],
        ["上一页", "下一页"],
    ]
    assert card["elements"][-3]["tag"] == "hr"
