from pathlib import Path

from openrelay.core import AppConfig, BackendConfig, FeishuConfig, IncomingMessage
from openrelay.session import SessionScopeResolver
from openrelay.storage import StateStore


class _NullLogger:
    def info(self, _message: str, *args: object) -> None:
        return None


def make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        cwd=tmp_path,
        port=3100,
        webhook_path="/feishu/webhook",
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "workspace",
        main_workspace_dir=tmp_path / "main",
        develop_workspace_dir=tmp_path / "develop",
        max_request_bytes=1024,
        max_session_messages=20,
        feishu=FeishuConfig(
            app_id="app",
            app_secret="secret",
            verify_token="verify-token",
            bot_open_id="ou_bot",
            allowed_open_ids={"ou_user"},
            admin_open_ids={"ou_admin"},
        ),
        backend=BackendConfig(default_backend="codex", default_safety_mode="workspace-write", codex_sessions_dir=tmp_path / "native"),
    )


def make_message(text: str, *, event_suffix: str = "", **overrides: str) -> IncomingMessage:
    suffix = event_suffix or text.replace(" ", "_")
    return IncomingMessage(
        event_id=f"evt_{suffix}",
        message_id=f"om_{suffix}",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id="ou_user",
        text=text,
        actionable=True,
        **overrides,
    )


def test_session_scope_prefers_root_id_scope(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    store = StateStore(config)
    resolver = SessionScopeResolver(config, store, _NullLogger())

    message = make_message(
        "follow up",
        event_suffix="follow_up",
        root_id="om_root",
        thread_id="omt_root",
        parent_id="om_parent",
    )

    assert resolver.build_session_key(message) == "p2p:oc_1:thread:om_root"
    store.close()


def test_session_scope_remembers_inbound_and_outbound_aliases(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    store = StateStore(config)
    resolver = SessionScopeResolver(config, store, _NullLogger())
    session_key = "p2p:oc_1:thread:om_root"
    message = make_message(
        "reply",
        event_suffix="reply",
        root_id="om_root",
        thread_id="omt_root",
        parent_id="om_parent",
    )

    resolver.remember_inbound_aliases(message, session_key)
    resolver.remember_outbound_aliases(message, session_key, [("om_bot_reply", "omt_bot_thread")])

    assert store.find_session_key_alias("p2p:oc_1:thread:omt_root") == session_key
    assert store.find_session_key_alias("p2p:oc_1:thread:om_parent") == session_key
    assert store.find_session_key_alias("p2p:oc_1:thread:om_reply") == session_key
    assert store.find_session_key_alias("p2p:oc_1:thread:om_bot_reply") == session_key
    assert store.find_session_key_alias("p2p:oc_1:thread:omt_bot_thread") == session_key
    store.close()


def test_card_action_detection_uses_explicit_source_kind(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    store = StateStore(config)
    resolver = SessionScopeResolver(config, store, _NullLogger())

    message = make_message(
        "/resume --page 2",
        event_suffix="resume_page_2",
        root_id="om_root",
        thread_id="om_root",
        reply_to_message_id="om_resume_card",
        source_kind="card_action",
    )

    assert resolver.is_card_action_message(message) is True
    store.close()
