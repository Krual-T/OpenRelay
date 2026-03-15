from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openrelay.core import AppConfig, SessionRecord, get_release_workspace, get_session_workspace_root


@dataclass(slots=True)
class SessionWorkspaceService:
    config: AppConfig

    def format_cwd(self, cwd: str, session: SessionRecord | None = None, release_channel: str | None = None) -> str:
        if release_channel:
            workspace_root = get_release_workspace(self.config, release_channel).resolve()
        elif session is not None:
            workspace_root = get_session_workspace_root(self.config, session).resolve()
        else:
            workspace_root = self.config.workspace_root.resolve()
        absolute = Path(cwd).expanduser().resolve() if cwd else workspace_root
        try:
            relative = absolute.relative_to(workspace_root)
        except ValueError:
            return str(absolute)
        return "." if str(relative) == "." else str(relative)

    def resolve_cwd(self, current_cwd: str, relative_path: str, session: SessionRecord) -> Path:
        workspace_root = get_session_workspace_root(self.config, session).resolve()
        base = Path(current_cwd).expanduser().resolve() if current_cwd else workspace_root
        requested = Path(relative_path.strip()).expanduser()
        target = requested.resolve() if requested.is_absolute() else (base / requested).resolve()
        if target != workspace_root and workspace_root not in target.parents:
            raise ValueError("path escapes workspace root")
        if not target.exists():
            raise ValueError(f"path does not exist: {relative_path}")
        if not target.is_dir():
            raise ValueError(f"not a directory: {relative_path}")
        return target
