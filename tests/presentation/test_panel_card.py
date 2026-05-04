from openrelay.presentation.panel import build_panel_card


def extract_commands(node) -> list[str]:
    commands: list[str] = []
    if isinstance(node, dict):
        value = node.get("value")
        if isinstance(value, dict) and value.get("command"):
            commands.append(str(value["command"]))
        for behavior in node.get("behaviors") or []:
            if isinstance(behavior, dict):
                behavior_value = behavior.get("value")
                if isinstance(behavior_value, dict) and behavior_value.get("command"):
                    commands.append(str(behavior_value["command"]))
        for child in node.values():
            commands.extend(extract_commands(child))
    elif isinstance(node, list):
        for child in node:
            commands.extend(extract_commands(child))
    return commands


def test_workspace_panel_card_uses_valid_form_container_for_search() -> None:
    card = build_panel_card(
        {
            "view": "workspace",
            "cwd": "~/Projects/openrelay",
            "browser_path": "/repo",
            "parent_path": "/",
            "browser_display": "~",
            "query": "api",
            "show_hidden": True,
            "page": 1,
            "total_pages": 1,
            "total_entries": 1,
            "workspace_entries": [
                {
                    "label": "openrelay",
                    "relative_path": "~/openrelay",
                    "absolute_path": "/repo/openrelay",
                    "state": "available",
                }
            ],
            "action_context": {"sessionKey": "p2p:oc_1", "rootId": "root_1"},
        }
    )

    assert card["schema"] == "2.0"
    form_blocks = [element for element in card["body"]["elements"] if element.get("tag") == "form"]
    assert len(form_blocks) == 1
    form = form_blocks[0]
    assert form["name"] == "workspace_search"
    assert form["elements"][0]["tag"] == "input"
    assert form["elements"][0]["name"] == "workspace_query"
    submit_button = form["elements"][1]["columns"][0]["elements"][0]
    assert submit_button["tag"] == "button"
    assert submit_button["name"] == "workspace_search_submit"
    assert submit_button["form_action_type"] == "submit"
    assert "--hidden" in submit_button["behaviors"][0]["value"]["command"]
    assert "显示中" in card["body"]["elements"][0]["content"]
    assert "action" not in [element.get("tag") for element in card["body"]["elements"]]


def test_panel_cards_do_not_offer_removed_panel_commands() -> None:
    base_info = {
        "session_id": "local_1",
        "current_title": "current",
        "cwd": "~/Projects/openrelay",
        "model": "codex",
        "provider": "app-server",
        "sandbox": "workspace-write",
        "context_usage": "unknown",
        "context_preview": "",
        "action_context": {"sessionKey": "p2p:oc_1", "rootId": "root_1"},
    }
    cards = [
        build_panel_card({**base_info, "view": "home", "sessions": [], "directory_shortcuts": []}),
        build_panel_card({**base_info, "view": "sessions", "sessions": [], "page": 1, "total_pages": 1, "sort_mode": "updated-desc"}),
        build_panel_card({**base_info, "view": "commands", "command_entries": []}),
        build_panel_card({**base_info, "view": "status", "status_entries": []}),
    ]

    for card in cards:
        assert all(not command.startswith("/panel") for command in extract_commands(card))
