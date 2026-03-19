import sqlite3
from pathlib import Path

from openrelay.core import AppConfig, BackendConfig, FeishuConfig
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



def test_state_create_and_resume_session(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    first = store.load_session("group:chat_1:sender:ou_1")
    store.append_message(first.session_id, "user", "hello")
    store.create_next_session(first.base_key, first, "fix bug", release_channel="develop", cwd=str(config.develop_workspace_dir))
    resumed = store.resume_session(first.base_key, first.session_id)
    assert resumed is not None
    assert resumed.session_id == first.session_id
    sessions = store.list_sessions(first.base_key)
    assert len(sessions) == 2
    assert sessions[0].active is True
    store.close()



def test_state_dedup_and_message_trim(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    session = store.load_session("p2p:chat_1")
    assert store.remember_message("evt_1") is False
    assert store.remember_message("evt_1") is True
    for index in range(5):
        store.append_message(session.session_id, "user", f"m{index}")
    messages = store.list_messages(session.session_id)
    assert len(messages) == 3
    assert messages[0]["content"] == "m2"
    store.close()


def test_state_migrates_legacy_database_name(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    legacy_db_path = config.data_dir / "agentmux.sqlite3"
    sqlite3.connect(legacy_db_path).close()

    store = StateStore(config)

    assert store.db_path == config.data_dir / "openrelay.sqlite3"
    assert store.db_path.exists()
    assert legacy_db_path.exists() is False
    store.close()


def test_state_directory_shortcut_crud(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)

    from openrelay.core import DirectoryShortcut

    saved = store.save_directory_shortcut(DirectoryShortcut(name="docs", path="docs", channels=("main",)))
    assert saved.name == "docs"
    assert store.get_directory_shortcut("DOCS") is not None
    assert store.list_directory_shortcuts()[0].channels == ("main",)
    assert store.remove_directory_shortcut("docs") is True
    assert store.get_directory_shortcut("docs") is None
    store.close()


def test_state_directory_shortcut_invalid_channels_fall_back_to_all(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    store.connection.execute(
        """
        INSERT INTO directory_shortcuts(name, path, channels_json, created_at, updated_at)
        VALUES('docs', 'docs', '["invalid"]', '2026-03-14T00:00:00Z', '2026-03-14T00:00:00Z')
        """
    )
    store.connection.commit()

    saved = store.get_directory_shortcut("docs")

    assert saved is not None
    assert saved.channels == ("all",)
    assert store.list_directory_shortcuts()[0].channels == ("all",)
    store.close()
