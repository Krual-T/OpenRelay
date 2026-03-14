import json
from pathlib import Path

from openrelay.core import AppConfig, BackendConfig, FeishuConfig
from openrelay.feishu import parse_card_action_event, parse_message_event, parse_webhook_body, split_text, strip_mentions



def make_config() -> AppConfig:
    base = Path.cwd()
    return AppConfig(
        cwd=base,
        port=3100,
        webhook_path="/feishu/webhook",
        data_dir=base / "data",
        workspace_root=base,
        main_workspace_dir=base,
        develop_workspace_dir=base,
        max_request_bytes=1024,
        max_session_messages=20,
        feishu=FeishuConfig(
            app_id="app",
            app_secret="secret",
            verify_token="verify-token",
            bot_open_id="ou_bot",
        ),
        backend=BackendConfig(codex_sessions_dir=base / "native"),
    )



def test_parse_webhook_challenge() -> None:
    parsed = parse_webhook_body(make_config(), {"type": "url_verification", "challenge": "ok"})
    assert parsed.type == "challenge"
    assert parsed.challenge == "ok"



def test_parse_actionable_group_message() -> None:
    config = make_config()
    parsed = parse_webhook_body(
        config,
        {
            "header": {"event_type": "im.message.receive_v1", "token": "verify-token", "event_id": "evt_1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user"}},
                "message": {
                    "message_id": "om_1",
                    "chat_id": "oc_1",
                    "chat_type": "group",
                    "message_type": "text",
                    "mentions": [{"key": "@_bot_1", "name": "Bot", "id": {"open_id": "ou_bot"}}],
                    "content": '{"text":"@Bot @_bot_1 hello"}',
                },
            },
        },
    )
    assert parsed.type == "message"
    assert parsed.message is not None
    assert parsed.message.event_id == "evt_1"
    assert parsed.message.actionable is True
    assert parsed.message.text == "hello"



def test_parse_message_event_p2p() -> None:
    config = make_config()
    parsed = parse_message_event(
        config,
        {
            "sender": {"sender_id": {"open_id": "ou_user"}},
            "message": {
                "message_id": "om_2",
                "chat_id": "oc_2",
                "chat_type": "p2p",
                "message_type": "text",
                "root_id": "root_1",
                "thread_id": "thread_1",
                "content": '{"text":"hi"}',
            },
        },
    )
    assert parsed.type == "message"
    assert parsed.message is not None
    assert parsed.message.actionable is True
    assert parsed.message.text == "hi"
    assert parsed.message.root_id == "root_1"
    assert parsed.message.thread_id == "thread_1"


def test_parse_message_event_image() -> None:
    config = make_config()
    parsed = parse_message_event(
        config,
        {
            "sender": {"sender_id": {"open_id": "ou_user"}},
            "message": {
                "message_id": "om_image_1",
                "chat_id": "oc_2",
                "chat_type": "p2p",
                "message_type": "image",
                "content": '{"image_key":"img_v2_123"}',
            },
        },
    )
    assert parsed.type == "message"
    assert parsed.message is not None
    assert parsed.message.actionable is True
    assert parsed.message.text == "[图片]"
    assert parsed.message.remote_image_keys == ("img_v2_123",)


def test_parse_message_event_post_with_text_and_image() -> None:
    config = make_config()
    parsed = parse_message_event(
        config,
        {
            "sender": {"sender_id": {"open_id": "ou_user"}},
            "message": {
                "message_id": "om_post_1",
                "chat_id": "oc_2",
                "chat_type": "p2p",
                "message_type": "post",
                "content": json.dumps(
                    {
                        "zh_cn": {
                            "title": "说明",
                            "content": [
                                [
                                    {"tag": "text", "text": "看看这张图"},
                                    {"tag": "img", "image_key": "img_v2_post_1"},
                                ]
                            ],
                        }
                    },
                    ensure_ascii=False,
                ),
            },
        },
    )
    assert parsed.type == "message"
    assert parsed.message is not None
    assert parsed.message.actionable is True
    assert parsed.message.text == "说明 看看这张图"
    assert parsed.message.remote_image_keys == ("img_v2_post_1",)


def test_parse_card_action_event() -> None:
    parsed = parse_card_action_event(
        {
            "token": "tok_1",
            "operator": {"open_id": "ou_user"},
            "action": {
                "value": {
                    "command": "/resume list --page 2 --sort active-first",
                    "root_id": "root_1",
                    "thread_id": "thread_1",
                    "session_key": "p2p:oc_1:thread:root_1",
                }
            },
            "context": {"open_chat_id": "oc_1", "open_message_id": "om_card_1"},
        }
    )
    assert parsed.type == "message"
    assert parsed.message is not None
    assert parsed.message.reply_to_message_id == "om_card_1"
    assert parsed.message.session_key == "p2p:oc_1:thread:root_1"
    assert parsed.message.thread_id == "thread_1"
    assert parsed.message.text == "/resume list --page 2 --sort active-first"


def test_parse_card_action_event_accepts_help_card_context_keys() -> None:
    parsed = parse_card_action_event(
        {
            "token": "tok_help_1",
            "operator": {"open_id": "ou_user"},
            "action": {
                "value": {
                    "command": "/status",
                    "rootId": "root_help_1",
                    "threadId": "thread_help_1",
                    "sessionKey": "p2p:oc_1:thread:root_help_1",
                    "sessionOwnerOpenId": "ou_user",
                }
            },
            "context": {"open_chat_id": "oc_1", "open_message_id": "om_help_card_1"},
        }
    )
    assert parsed.type == "message"
    assert parsed.message is not None
    assert parsed.message.reply_to_message_id == "om_help_card_1"
    assert parsed.message.root_id == "root_help_1"
    assert parsed.message.thread_id == "thread_help_1"
    assert parsed.message.session_key == "p2p:oc_1:thread:root_help_1"
    assert parsed.message.session_owner_open_id == "ou_user"
    assert parsed.message.text == "/status"



def test_parse_webhook_without_verify_token() -> None:
    config = make_config()
    config.feishu.verify_token = ""
    parsed = parse_webhook_body(
        config,
        {
            "header": {"event_type": "im.message.receive_v1", "event_id": "evt_no_token"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user"}},
                "message": {
                    "message_id": "om_no_token",
                    "chat_id": "oc_no_token",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "content": '{"text":"hi"}',
                },
            },
        },
    )
    assert parsed.type == "message"
    assert parsed.message is not None
    assert parsed.message.event_id == "evt_no_token"



def test_strip_mentions_and_split_text() -> None:
    assert strip_mentions('<at user_id="1">Bot</at> hi', []) == "hi"
    chunks = split_text("a" * 8000)
    assert len(chunks) == 3
    assert "".join(chunks) == "a" * 8000
