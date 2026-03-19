from pathlib import Path

import pytest

from openrelay.core import DirectoryShortcut, SessionRecord
from openrelay.session import SessionShortcutService, SessionWorkspaceService
from openrelay.storage import StateStore
from tests.support.app import make_app_config, prepare_app_dirs


def make_config(tmp_path: Path):
    projects_dir = tmp_path / "home" / "Projects"
    return make_app_config(
        tmp_path,
        workspace_root=tmp_path / "home",
        main_workspace_dir=projects_dir,
        develop_workspace_dir=tmp_path / "home" / "develop",
        workspace_default_dir=projects_dir,
    )


def test_workspace_resolve_cwd_rejects_escape(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    prepare_app_dirs(config)
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
    prepare_app_dirs(config)
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


def test_workspace_directory_page_lists_visible_entries_for_current_browser_path(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    prepare_app_dirs(config)
    (config.main_workspace_dir / "docs").mkdir()
    (config.main_workspace_dir / "src").mkdir()
    (config.main_workspace_dir / "src" / "api").mkdir(parents=True)
    (config.main_workspace_dir / "src" / "core").mkdir(parents=True)
    (config.main_workspace_dir / ".git").mkdir()
    session = SessionRecord(
        session_id="s_1",
        base_key="p2p:oc_1",
        backend="codex",
        cwd=str(config.main_workspace_dir / "src"),
        release_channel="main",
    )
    workspace = SessionWorkspaceService(config)

    page = workspace.list_workspace_directories(session, browser_path=config.main_workspace_dir / "src", page_size=10)

    assert page.browser_path == str((config.main_workspace_dir / "src").resolve())
    assert page.parent_path == str(config.main_workspace_dir.resolve())
    assert [entry.relative_path for entry in page.entries] == ["Projects/src/api", "Projects/src/core"]
    assert [entry.state for entry in page.entries] == ["available", "available"]


def test_workspace_directory_page_supports_query_filter(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    prepare_app_dirs(config)
    (config.main_workspace_dir / "api-server").mkdir()
    (config.main_workspace_dir / "web-app").mkdir()
    session = SessionRecord(
        session_id="s_1",
        base_key="p2p:oc_1",
        backend="codex",
        cwd=str(config.main_workspace_dir),
        release_channel="main",
    )
    workspace = SessionWorkspaceService(config)

    page = workspace.list_workspace_directories(session, query="api", page_size=10)

    assert page.query == "api"
    assert [entry.label for entry in page.entries] == ["api-server"]


def test_workspace_directory_page_hides_hidden_directories_by_default_but_can_show_them(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    prepare_app_dirs(config)
    (config.main_workspace_dir / ".codex").mkdir()
    (config.main_workspace_dir / "docs").mkdir()
    session = SessionRecord(
        session_id="s_1",
        base_key="p2p:oc_1",
        backend="codex",
        cwd=str(config.main_workspace_dir),
        release_channel="main",
    )
    workspace = SessionWorkspaceService(config)

    default_page = workspace.list_workspace_directories(session, page_size=10)
    hidden_page = workspace.list_workspace_directories(session, show_hidden=True, page_size=10)

    assert default_page.show_hidden is False
    assert [entry.label for entry in default_page.entries] == ["docs"]
    assert hidden_page.show_hidden is True
    assert [entry.label for entry in hidden_page.entries] == [".codex", "docs"]


def test_workspace_browser_defaults_to_projects_but_root_is_home(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    prepare_app_dirs(config)
    (config.workspace_root / "Projects").mkdir(exist_ok=True)
    (config.workspace_root / "Downloads").mkdir()
    session = SessionRecord(
        session_id="s_1",
        base_key="p2p:oc_1",
        backend="codex",
        cwd=str(config.main_workspace_dir),
        release_channel="main",
    )
    workspace = SessionWorkspaceService(config)

    default_page = workspace.list_workspace_directories(session, page_size=10)
    root_page = workspace.list_workspace_directories(session, browser_path=config.workspace_root, page_size=10)

    assert default_page.browser_path == str(config.main_workspace_dir.resolve())
    assert workspace.format_workspace_picker_path(root_page.browser_path, session) == "~"
    assert [entry.label for entry in root_page.entries] == ["develop", "Downloads", "Projects"]
