from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openrelay.core import AppConfig, SessionRecord, get_release_workspace, get_session_workspace_root


@dataclass(slots=True)
class WorkspaceDirectoryEntry:
    label: str
    relative_path: str
    absolute_path: str
    state: str


@dataclass(slots=True)
class WorkspaceDirectoryPage:
    entries: tuple[WorkspaceDirectoryEntry, ...]
    browser_path: str
    parent_path: str
    query: str
    page: int
    total_pages: int
    total_entries: int
    has_previous: bool
    has_next: bool


@dataclass(slots=True)
class SessionWorkspaceService:
    config: AppConfig

    def workspace_root(
        self,
        session: SessionRecord | None = None,
        release_channel: str | None = None,
    ) -> Path:
        if release_channel:
            return get_release_workspace(self.config, release_channel).resolve()
        if session is not None:
            return get_session_workspace_root(self.config, session).resolve()
        return self.config.workspace_root.resolve()

    def format_cwd(self, cwd: str, session: SessionRecord | None = None, release_channel: str | None = None) -> str:
        workspace_root = self.workspace_root(session, release_channel)
        absolute = Path(cwd).expanduser().resolve() if cwd else workspace_root
        try:
            relative = absolute.relative_to(workspace_root)
        except ValueError:
            return str(absolute)
        return "." if str(relative) == "." else str(relative)

    def format_workspace_picker_path(self, path: str | Path, session: SessionRecord | None = None) -> str:
        workspace_root = self.workspace_root(session)
        absolute = Path(path).expanduser().resolve()
        try:
            relative = absolute.relative_to(workspace_root)
        except ValueError:
            return str(absolute)
        return "~" if str(relative) == "." else f"~/{relative}"

    def resolve_directory(self, raw_path: str, *, workspace_root: Path, base: Path | None = None) -> Path:
        requested = Path(raw_path.strip()).expanduser()
        if not raw_path.strip():
            raise ValueError("path is empty")
        parent = base or workspace_root
        target = requested.resolve() if requested.is_absolute() else (parent / requested).resolve()
        if target != workspace_root and workspace_root not in target.parents:
            raise ValueError("path escapes workspace root")
        if not target.exists():
            raise ValueError(f"path does not exist: {raw_path}")
        if not target.is_dir():
            raise ValueError(f"not a directory: {raw_path}")
        return target

    def resolve_cwd(self, current_cwd: str, relative_path: str, session: SessionRecord) -> Path:
        workspace_root = self.workspace_root(session)
        base = Path(current_cwd).expanduser().resolve() if current_cwd else workspace_root
        return self.resolve_directory(relative_path, workspace_root=workspace_root, base=base)

    def resolve_workspace_selection(self, raw_path: str, session: SessionRecord) -> Path:
        workspace_root = self.workspace_root(session)
        return self.resolve_directory(raw_path, workspace_root=workspace_root, base=workspace_root)

    def list_workspace_directories(
        self,
        session: SessionRecord,
        *,
        browser_path: str | Path | None = None,
        query: str = "",
        page: int = 1,
        page_size: int = 6,
    ) -> WorkspaceDirectoryPage:
        workspace_root = self.workspace_root(session)
        browser = self.resolve_directory(str(browser_path or workspace_root), workspace_root=workspace_root, base=workspace_root)
        current = Path(session.cwd).expanduser().resolve() if session.cwd else workspace_root
        normalized_query = query.strip().lower()
        visible_directories = sorted(
            (
                child.resolve()
                for child in browser.iterdir()
                if child.is_dir() and not child.name.startswith(".")
            ),
            key=lambda item: item.name.lower(),
        )
        if normalized_query:
            visible_directories = [item for item in visible_directories if normalized_query in item.name.lower()]
        entries = tuple(self._build_workspace_directory_entry(workspace_root, current, target) for target in visible_directories)
        total_entries = len(entries)
        safe_page_size = max(page_size, 1)
        total_pages = max((total_entries + safe_page_size - 1) // safe_page_size, 1)
        current_page = min(max(page, 1), total_pages)
        start = (current_page - 1) * safe_page_size
        visible_entries = entries[start:start + safe_page_size]
        return WorkspaceDirectoryPage(
            entries=visible_entries,
            browser_path=str(browser),
            parent_path=str(browser.parent if browser != workspace_root else workspace_root),
            query=query.strip(),
            page=current_page,
            total_pages=total_pages,
            total_entries=total_entries,
            has_previous=current_page > 1,
            has_next=start + safe_page_size < total_entries,
        )

    def _build_workspace_directory_entry(self, workspace_root: Path, current: Path, target: Path) -> WorkspaceDirectoryEntry:
        relative_path = "." if target == workspace_root else str(target.relative_to(workspace_root))
        if target == workspace_root:
            label = "工作区根目录"
        else:
            label = target.name
        state = "available"
        if current == target:
            state = "current"
        elif target in current.parents:
            state = "active_branch"
        return WorkspaceDirectoryEntry(
            label=label,
            relative_path=relative_path,
            absolute_path=str(target),
            state=state,
        )
