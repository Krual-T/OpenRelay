from openrelay.session_list_card import build_session_list_card



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
    assert "/resume list --page 1 --sort updated-desc" in commands
    assert "/resume list --page 3 --sort updated-desc" in commands
    assert "/resume list --page 1 --sort active-first" in commands
    assert "/resume s_6 --page 2 --sort updated-desc" in commands
