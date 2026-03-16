from types import SimpleNamespace

from openrelay.core.models import SessionRecord
from openrelay.presentation.session import build_backend_session_list_card, build_session_list_card
from openrelay.runtime.panel_service import RuntimePanelService



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


def test_backend_session_list_card_uses_quote_blocks_and_backend_title() -> None:
    card = build_backend_session_list_card(
        {
            "page": 1,
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
    assert card["elements"][0]["text"]["content"] == "> **1. task 1** · 当前\n> 2026-03-16 18:00:00 · status=idle\n> `thread_1`"


def test_runtime_panel_service_backend_session_card_limits_to_three_and_formats_seconds() -> None:
    service = object.__new__(RuntimePanelService)
    service.session_presentation = SimpleNamespace(shorten=lambda text, length: text if len(text) <= length else text[:length])
    service.workspace = SimpleNamespace(format_cwd=lambda cwd, session: "openrelay")

    session = SessionRecord(
        session_id="local_1",
        base_key="p2p:oc_1",
        backend="codex",
        cwd="/tmp/openrelay",
        native_session_id="thread_2",
    )
    card, fallback = RuntimePanelService._build_session_list_card_from_rows(
        service,
        session,
        1,
        {"sessionKey": "p2p:oc_1"},
        [
            {"session_id": "thread_1", "preview": "preview 1", "cwd": "/tmp/openrelay", "updated_at": "2026-03-16T10:00:00Z", "status": "idle", "name": "task 1"},
            {"session_id": "thread_2", "preview": "preview 2", "cwd": "/tmp/openrelay", "updated_at": "2026-03-15T10:00:00Z", "status": "idle", "name": "task 2"},
            {"session_id": "thread_3", "preview": "preview 3", "cwd": "/tmp/openrelay", "updated_at": "2026-03-14T10:00:00Z", "status": "idle", "name": "task 3"},
            {"session_id": "thread_4", "preview": "preview 4", "cwd": "/tmp/openrelay", "updated_at": "2026-03-13T10:00:00Z", "status": "idle", "name": "task 4"},
        ],
    )

    markdown_blocks = [element["text"]["content"] for element in card["elements"] if element.get("tag") == "div"]
    assert len(markdown_blocks) == 3
    assert markdown_blocks[0] == "> **1. task 1**\n> 2026-03-16 18:00:00 · status=idle · cwd=openrelay\n> `thread_1`"
    assert markdown_blocks[1] == "> **2. task 2** · 当前\n> 2026-03-15 18:00:00 · status=idle · cwd=openrelay\n> `thread_2`"
    assert "thread_4" not in str(card)
    assert "预览" not in str(card)
    assert "preview" not in fallback
    assert "2026-03-16 18:00:00" in fallback
