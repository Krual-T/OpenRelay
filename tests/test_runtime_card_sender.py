import logging

import pytest

from openrelay.core import AppConfig, BackendConfig, FeishuConfig, IncomingMessage
from openrelay.runtime.card_sender import CommandCardSender
from openrelay.runtime.replying import RuntimeReplyPolicy
from openrelay.session.scope.resolver import SessionScopeResolver
from openrelay.storage import StateStore


class _FakeMessenger:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
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
        if self.should_fail:
            raise RuntimeError("boom")
        return object()


def make_config(tmp_path) -> AppConfig:
    return AppConfig(
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


@pytest.mark.asyncio
async def test_command_card_sender_updates_card_action_in_place(tmp_path) -> None:
    config = make_config(tmp_path)
    for path in (config.data_dir, config.develop_workspace_dir, config.backend.codex_sessions_dir):
        path.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    scope = SessionScopeResolver(config, store, logging.getLogger("test.card.sender"))
    fallback_calls: list[tuple[str, str]] = []

    async def reply_fallback(message: IncomingMessage, text: str, command_name: str) -> None:
        fallback_calls.append((command_name, text))

    sender = CommandCardSender(
        _FakeMessenger(),  # type: ignore[arg-type]
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
    config = make_config(tmp_path)
    for path in (config.data_dir, config.develop_workspace_dir, config.backend.codex_sessions_dir):
        path.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    scope = SessionScopeResolver(config, store, logging.getLogger("test.card.sender"))
    fallback_calls: list[tuple[str, str]] = []

    async def reply_fallback(message: IncomingMessage, text: str, command_name: str) -> None:
        fallback_calls.append((command_name, text))

    sender = CommandCardSender(
        _FakeMessenger(should_fail=True),  # type: ignore[arg-type]
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
