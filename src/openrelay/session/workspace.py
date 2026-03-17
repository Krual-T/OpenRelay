from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openrelay.core import AppConfig, SessionRecord, get_release_workspace, get_session_workspace_root


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
