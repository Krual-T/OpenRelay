from pathlib import Path

import pytest

from openrelay.core import AppConfig, BackendConfig, DirectoryShortcut, FeishuConfig, SessionRecord
from openrelay.session import SessionShortcutService, SessionWorkspaceService
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
        max_session_messages=20,
        feishu=FeishuConfig(app_id="app", app_secret="secret", verify_token="verify-token", bot_open_id="ou_bot"),
        backend=BackendConfig(codex_sessions_dir=tmp_path / "native"),
    )


def prepare_dirs(config: AppConfig) -> None:
    for path in (config.data_dir, config.workspace_root, config.main_workspace_dir, config.develop_workspace_dir, config.backend.codex_sessions_dir):
        path.mkdir(parents=True, exist_ok=True)


def test_workspace_resolve_cwd_rejects_escape(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    prepare_dirs(config)
    workspace = SessionWorkspaceService(config)
    session = SessionRecord(
        session_id="s_1",
        base_key="p2p:oc_1",
        backend="codex",
        cwd=str(config.main_workspace_dir),
        release_channel="main",
    )

    with pytest.raises(ValueError, match="path escapes workspace root"):
        workspace.resolve_cwd(str(config.main_workspace_dir), "../outside", session)


def test_directory_shortcut_resolution_reuses_workspace_guardrails(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    prepare_dirs(config)
    (config.main_workspace_dir / "project").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    store = StateStore(config)
    workspace = SessionWorkspaceService(config)
    shortcuts = SessionShortcutService(config, store, workspace)
    store.save_directory_shortcut(DirectoryShortcut(name="project", path="project", channels=("all",)))
    store.save_directory_shortcut(DirectoryShortcut(name="outside", path=str(outside), channels=("all",)))

    session = SessionRecord(
        session_id="s_1",
        base_key="p2p:oc_1",
        backend="codex",
        cwd=str(config.main_workspace_dir),
        release_channel="main",
    )

    assert shortcuts.resolve_directory_shortcut("project", session) == (config.main_workspace_dir / "project").resolve()
    assert shortcuts.resolve_directory_shortcut("outside", session) is None
    store.close()


def test_workspace_directory_page_lists_visible_top_level_entries(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    prepare_dirs(config)
    (config.main_workspace_dir / "docs").mkdir()
    (config.main_workspace_dir / "src").mkdir()
    (config.main_workspace_dir / ".git").mkdir()
    session = SessionRecord(
        session_id="s_1",
        base_key="p2p:oc_1",
        backend="codex",
        cwd=str(config.main_workspace_dir / "src"),
        release_channel="main",
    )
    workspace = SessionWorkspaceService(config)

    page = workspace.list_workspace_directories(session, page_size=10)

    assert [entry.relative_path for entry in page.entries] == [".", "docs", "src"]
    assert [entry.state for entry in page.entries] == ["active_branch", "available", "current"]
