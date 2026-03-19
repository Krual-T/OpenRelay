import logging
from types import SimpleNamespace

import pytest

from openrelay.core import AppConfig, BackendConfig, FeishuConfig, IncomingMessage
from openrelay.core.models import SessionRecord
from openrelay.runtime.panel_service import RuntimePanelService
from openrelay.runtime.replying import RuntimeReplyPolicy
from openrelay.session.scope.resolver import SessionScopeResolver
from openrelay.storage import StateStore


class _FakeMessenger:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def send_interactive_card(
        self,
        chat_id: str,
        card: dict[str, object],
        *,
        reply_to_message_id: str = "",
        root_id: str = "",
        force_new_message: bool = False,
        update_message_id: str = "",
    ) -> object:
        self.calls.append(
            {
                "chat_id": chat_id,
                "card": card,
                "reply_to_message_id": reply_to_message_id,
                "root_id": root_id,
                "force_new_message": force_new_message,
                "update_message_id": update_message_id,
            }
        )
        return object()


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
    assert markdown_blocks[0] == "**1. task 1**\n2026-03-16 18:00:00 · status=idle · cwd=openrelay\n`thread_1`"
    assert markdown_blocks[1] == "**2. task 2** · 当前\n2026-03-15 18:00:00 · status=idle · cwd=openrelay\n`thread_2`"
    assert "thread_4" not in str(card)
    assert card["elements"][-3]["tag"] == "hr"
    pagination_rows = [element["actions"] for element in card["elements"] if element.get("tag") == "action"][-2:]
    assert [[action["text"]["content"] for action in row] for row in pagination_rows] == [["1", "2"], ["下一页"]]
    assert "预览" not in str(card)
    assert "preview" not in fallback
    assert "2026-03-16 18:00:00" in fallback


@pytest.mark.asyncio
async def test_runtime_panel_service_updates_resume_card_in_place_for_card_actions(tmp_path) -> None:
    config = AppConfig(
        cwd=tmp_path,
        port=3100,
        webhook_path="/feishu/webhook",
        data_dir=tmp_path / "data",
        workspace_root=tmp_path,
        main_workspace_dir=tmp_path,
        develop_workspace_dir=tmp_path / "develop",
        max_request_bytes=1024,
        max_session_messages=20,
        feishu=FeishuConfig(app_id="app", app_secret="secret", verify_token="verify-token", bot_open_id="ou_bot"),
        backend=BackendConfig(codex_sessions_dir=tmp_path / "native"),
    )
    for path in (config.data_dir, config.develop_workspace_dir, config.backend.codex_sessions_dir):
        path.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    scope = SessionScopeResolver(config, store, logging.getLogger("test.resume.card.update"))
    messenger = _FakeMessenger()

    service = RuntimePanelService(
        config=config,
        messenger=messenger,  # type: ignore[arg-type]
        backend_descriptors={},
        session_browser=SimpleNamespace(),
        session_presentation=SimpleNamespace(),
        workspace=SimpleNamespace(),
        shortcuts=SimpleNamespace(),
        reply_policy=RuntimeReplyPolicy(config, scope),
        reply_fallback=None,  # type: ignore[arg-type]
        presenter=SimpleNamespace(),
        runtime_service=None,
    )

    async def _build_payload(message, session, page, action_context):
        _ = message, session, page, action_context
        return ({"header": {"title": {"content": "resume"}}, "elements": []}, "fallback")

    async def _reply_fallback(message, text, command_name):
        raise AssertionError(f"unexpected fallback: {command_name} {text}")

    async def _send_session_list(message, session_key, session, page, sort_mode):
        action_context = service.reply_policy.build_card_action_context(message, session_key)
        card, fallback_text = await _build_payload(message, session, page, action_context)
        try:
            await service.messenger.send_interactive_card(
                message.chat_id,
                card,
                reply_to_message_id=service.reply_policy.command_reply_target(message),
                root_id=service.reply_policy.root_id_for_message(message),
                force_new_message=service.reply_policy.should_force_new_message_for_command_card(message),
                update_message_id=service.reply_policy.command_card_update_target(message),
            )
        except Exception:
            await _reply_fallback(message, fallback_text, "/resume")

    session = SessionRecord(session_id="local_1", base_key="p2p:oc_1", backend="codex", cwd=str(tmp_path))
    message = IncomingMessage(
        event_id="evt_resume_card_page_2",
        message_id="om_resume_card",
        reply_to_message_id="om_resume_card",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id="ou_user",
        source_kind="card_action",
        text="/resume --page 2",
        actionable=True,
    )

    await _send_session_list(message, session.base_key, session, 2, "updated-desc")

    assert messenger.calls == [
        {
            "chat_id": "oc_1",
            "card": {"header": {"title": {"content": "resume"}}, "elements": []},
            "reply_to_message_id": "om_resume_card",
            "root_id": "",
            "force_new_message": False,
            "update_message_id": "om_resume_card",
        }
    ]
    store.close()
