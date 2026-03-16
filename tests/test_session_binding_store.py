from pathlib import Path

from openrelay.core import AppConfig, BackendConfig, FeishuConfig
from openrelay.session.store import SessionBindingStore
from openrelay.session.models import RelaySessionBinding
from openrelay.storage import StateStore


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
        max_session_messages=3,
        feishu=FeishuConfig(app_id="app", app_secret="secret", verify_token="verify-token", bot_open_id="ou_bot"),
        backend=BackendConfig(codex_sessions_dir=tmp_path / "native"),
    )


def test_session_binding_store_persists_and_syncs_session_record(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    session = store.load_session("group:chat_1:sender:ou_1")
    bindings = SessionBindingStore(store)

    binding = RelaySessionBinding(
        relay_session_id=session.session_id,
        backend="codex",
        native_session_id="thread_1",
        cwd=str(config.main_workspace_dir),
        model="gpt-test",
        safety_mode="danger-full-access",
        feishu_chat_id="chat_1",
        feishu_thread_id="thread_scope_1",
    )
    bindings.save(binding)
    bindings.update_native_session_id(session.session_id, "thread_2")

    saved = bindings.get(session.session_id)
    scoped = bindings.find_by_feishu_scope("chat_1", "thread_scope_1")
    synced_session = store.get_session(session.session_id)

    assert saved is not None
    assert scoped is not None
    assert saved.native_session_id == "thread_2"
    assert scoped.relay_session_id == session.session_id
    assert synced_session.native_session_id == "thread_2"
    assert synced_session.model_override == "gpt-test"
    assert synced_session.safety_mode == "danger-full-access"
    store.close()


def test_session_binding_store_lists_recent_by_backend(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    first = store.load_session("group:chat_1:sender:ou_1")
    second = store.create_next_session(first.base_key, first, backend="claude")
    bindings = SessionBindingStore(store)
    bindings.save(
        RelaySessionBinding(
            relay_session_id=first.session_id,
            backend="codex",
            native_session_id="thread_1",
            cwd=first.cwd,
            model="",
            safety_mode=first.safety_mode,
            feishu_chat_id="chat_1",
            feishu_thread_id="",
        )
    )
    bindings.save(
        RelaySessionBinding(
            relay_session_id=second.session_id,
            backend="claude",
            native_session_id="thread_2",
            cwd=second.cwd,
            model="",
            safety_mode=second.safety_mode,
            feishu_chat_id="chat_1",
            feishu_thread_id="thread_2",
        )
    )

    recent = bindings.list_recent(backend="claude")

    assert [entry.relay_session_id for entry in recent] == [second.session_id]
    store.close()
