from pathlib import Path
import json

from openrelay.config import AppConfig, BackendConfig, FeishuConfig
from openrelay.models import SessionRecord
from openrelay.native_sessions import find_native_session, import_native_session, list_native_sessions
from openrelay.state import StateStore



def make_config(tmp_path: Path) -> AppConfig:
    native_dir = tmp_path / "native"
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
        backend=BackendConfig(codex_sessions_dir=native_dir),
    )



def write_native_session(file_path: Path, session_id: str, cwd: Path, first_message: str) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"type": "session_meta", "timestamp": "2026-03-09T00:00:00+00:00", "payload": {"id": session_id, "cwd": str(cwd)}}),
        json.dumps({"type": "event_msg", "payload": {"type": "user_message", "message": first_message}}),
    ]
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")



def test_list_native_sessions_prefers_workspace_matches(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    for path in [config.workspace_root, config.main_workspace_dir, config.develop_workspace_dir, config.backend.codex_sessions_dir]:
        path.mkdir(parents=True, exist_ok=True)
    write_native_session(config.backend.codex_sessions_dir / "main" / "a.jsonl", "native_main", config.main_workspace_dir / "repo", "fix main bug")
    write_native_session(config.backend.codex_sessions_dir / "ext" / "b.jsonl", "native_ext", tmp_path / "outside", "inspect external")
    entries = list_native_sessions(config, limit=10)
    assert len(entries) == 2
    assert entries[0].session_id == "native_main"
    assert entries[0].matches_workspace is True



def test_find_and_import_native_session(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    for path in [config.workspace_root, config.main_workspace_dir, config.develop_workspace_dir, config.backend.codex_sessions_dir]:
        path.mkdir(parents=True, exist_ok=True)
    write_native_session(config.backend.codex_sessions_dir / "main" / "c.jsonl", "native_resume", config.main_workspace_dir / "repo", "resume me")
    native = find_native_session(config, "native_res")
    assert native is not None
    store = StateStore(config)
    current = SessionRecord(session_id="s_local", base_key="p2p:oc_1", backend="codex", cwd=str(config.workspace_root), release_channel="main")
    imported = import_native_session(store, current.base_key, native, current)
    assert imported.session_id == "native_resume"
    assert imported.native_session_id == "native_resume"
    assert imported.cwd == str(config.main_workspace_dir / "repo")
    store.close()
