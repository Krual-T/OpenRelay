from pathlib import Path
import json

from openrelay.config import AppConfig, BackendConfig, FeishuConfig
from openrelay.session_browser import DEFAULT_SESSION_LIST_SORT, SESSION_SORT_ACTIVE, SessionBrowser
from openrelay.state import StateStore



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
        feishu=FeishuConfig(app_id="app", app_secret="secret", verify_token="verify-token", bot_open_id="ou_bot"),
        backend=BackendConfig(codex_sessions_dir=tmp_path / "native"),
    )



def prepare_dirs(config: AppConfig) -> None:
    for path in [config.workspace_root, config.main_workspace_dir, config.develop_workspace_dir, config.backend.codex_sessions_dir]:
        path.mkdir(parents=True, exist_ok=True)



def write_native_session(file_path: Path, session_id: str, cwd: Path, first_message: str) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"type": "session_meta", "timestamp": "2026-03-09T00:00:00+00:00", "payload": {"id": session_id, "cwd": str(cwd)}}),
        json.dumps({"type": "event_msg", "payload": {"type": "user_message", "message": first_message}}),
    ]
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")



def test_session_browser_lists_only_local_backend_sessions(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    prepare_dirs(config)
    store = StateStore(config)
    browser = SessionBrowser(config, store)
    session_key = "p2p:oc_1"
    active = store.load_session(session_key)
    active.label = "current task"
    store.append_message(active.session_id, "user", "hello")
    store.save_session(active)
    previous = store.create_next_session(session_key, active, "older task")
    previous = store.get_session(previous.session_id)
    store.resume_session(session_key, active.session_id)
    entries = browser.list_entries(session_key, store.load_session(session_key), limit=10)

    assert [entry.session_id for entry in entries] == [previous.session_id, active.session_id]
    assert entries[0].resume_token == previous.session_id
    assert entries[1].active is True
    assert entries[1].origin == "local"
    store.close()


def test_session_browser_resume_latest_uses_local_backend_sessions(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    prepare_dirs(config)
    store = StateStore(config)
    browser = SessionBrowser(config, store)
    session_key = "p2p:oc_1"
    current = store.load_session(session_key)
    previous = store.create_next_session(session_key, current, "older task")
    previous.native_session_id = "native_previous"
    store.save_session(previous)
    store.resume_session(session_key, current.session_id)

    result = browser.resume(session_key, current, "latest", browser.list_entries(session_key, current, limit=10))

    assert result is not None
    assert result.session.session_id == previous.session_id
    assert result.session.native_session_id == "native_previous"
    store.close()



def test_session_browser_builds_paged_view_with_default_updated_sort(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    prepare_dirs(config)
    store = StateStore(config)
    browser = SessionBrowser(config, store)
    session_key = "p2p:oc_1"
    active = store.load_session(session_key)
    active.label = "current"
    store.save_session(active)
    created: list[str] = []
    for index in range(6):
        next_session = store.create_next_session(session_key, active, f"session-{index}")
        created.append(next_session.session_id)
    store.resume_session(session_key, active.session_id)

    updated_page = browser.list_page(session_key, store.load_session(session_key), page=2, page_size=3, sort_mode=DEFAULT_SESSION_LIST_SORT)
    active_page = browser.list_page(session_key, store.load_session(session_key), page=1, page_size=3, sort_mode=SESSION_SORT_ACTIVE)

    assert updated_page.page == 2
    assert updated_page.has_previous is True
    assert updated_page.start_index == 4
    assert len(updated_page.entries) == 3
    assert active_page.entries[0].active is True
    store.close()
