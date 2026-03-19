import logging

import pytest

from openrelay.core import IncomingMessage
from openrelay.runtime.card_sender import CommandCardSender
from openrelay.runtime.replying import RuntimeReplyPolicy
from openrelay.session.scope.resolver import SessionScopeResolver
from openrelay.storage import StateStore
from tests.support.app import make_app_config, prepare_app_dirs
from tests.support.messenger import RecordingInteractiveMessenger


@pytest.mark.asyncio
async def test_command_card_sender_updates_card_action_in_place(tmp_path) -> None:
    config = make_app_config(
        tmp_path,
        workspace_root=tmp_path,
        main_workspace_dir=tmp_path,
        develop_workspace_dir=tmp_path / "develop",
    )
    prepare_app_dirs(config)
    store = StateStore(config)
    scope = SessionScopeResolver(config, store, logging.getLogger("test.card.sender"))
    fallback_calls: list[tuple[str, str]] = []

    async def reply_fallback(message: IncomingMessage, text: str, command_name: str) -> None:
        fallback_calls.append((command_name, text))

    sender = CommandCardSender(
        RecordingInteractiveMessenger(),  # type: ignore[arg-type]
        RuntimeReplyPolicy(config, scope),
        reply_fallback,
    )
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

    await sender.send(
        message,
        {"header": {"title": {"content": "resume"}}, "elements": []},
        fallback_text="fallback",
        command_name="/resume",
    )

    assert fallback_calls == []
    assert sender.messenger.calls == [
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


@pytest.mark.asyncio
async def test_command_card_sender_falls_back_to_text_on_send_error(tmp_path) -> None:
    config = make_app_config(
        tmp_path,
        workspace_root=tmp_path,
        main_workspace_dir=tmp_path,
        develop_workspace_dir=tmp_path / "develop",
    )
    prepare_app_dirs(config)
    store = StateStore(config)
    scope = SessionScopeResolver(config, store, logging.getLogger("test.card.sender"))
    fallback_calls: list[tuple[str, str]] = []

    async def reply_fallback(message: IncomingMessage, text: str, command_name: str) -> None:
        fallback_calls.append((command_name, text))

    sender = CommandCardSender(
        RecordingInteractiveMessenger(should_fail=True),  # type: ignore[arg-type]
        RuntimeReplyPolicy(config, scope),
        reply_fallback,
    )
    message = IncomingMessage(
        event_id="evt_help",
        message_id="om_help",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id="ou_user",
        text="/help",
        actionable=True,
    )

    await sender.send(message, {"elements": []}, fallback_text="help text", command_name="/help")

    assert fallback_calls == [("/help", "help text")]
    store.close()
