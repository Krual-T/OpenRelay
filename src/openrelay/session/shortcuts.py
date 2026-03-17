from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

from openrelay.core import AppConfig, DirectoryShortcut, SessionRecord, infer_release_channel
from openrelay.storage import StateStore

from .workspace import SessionWorkspaceService


@dataclass(slots=True)
class SessionShortcutService:
    config: AppConfig
    store: StateStore
    workspace: SessionWorkspaceService

    def build_directory_shortcut_entries(self, session: SessionRecord, limit: int = 4) -> list[dict[str, str]]:
        channel = infer_release_channel(self.config, session)
        workspace_root = self.workspace.workspace_root(session)
        entries: list[dict[str, str]] = []
        for shortcut in self.list_directory_shortcuts():
            if "all" not in shortcut.channels and channel not in shortcut.channels:
                continue
            target = self._resolve_directory_shortcut_target(shortcut.path, workspace_root)
            if target is None:
                continue
            entries.append(
                {
                    "label": shortcut.name,
                    "display_path": self.workspace.format_cwd(str(target), None, channel),
                    "command": f"/cwd {shlex.quote(str(target))}",
                    "channels": ",".join(shortcut.channels),
                    "raw_path": shortcut.path,
                }
            )
            if len(entries) >= limit:
                break
        return entries

    def list_directory_shortcuts(self) -> tuple[DirectoryShortcut, ...]:
        merged: list[DirectoryShortcut] = []
        seen: set[str] = set()
        for shortcut in (*self.store.list_directory_shortcuts(), *self.config.directory_shortcuts):
            name_key = shortcut.name.strip().lower()
            if not name_key or name_key in seen:
                continue
            seen.add(name_key)
            merged.append(shortcut)
        return tuple(merged)

    def resolve_directory_shortcut(self, name: str, session: SessionRecord) -> Path | None:
        requested_name = name.strip().lower()
        if not requested_name:
            return None
        channel = infer_release_channel(self.config, session)
        workspace_root = self.workspace.workspace_root(session)
        for shortcut in self.list_directory_shortcuts():
            if shortcut.name.strip().lower() != requested_name:
                continue
            if "all" not in shortcut.channels and channel not in shortcut.channels:
                return None
            return self._resolve_directory_shortcut_target(shortcut.path, workspace_root)
        return None

    def _resolve_directory_shortcut_target(self, raw_path: str, workspace_root: Path) -> Path | None:
        normalized_path = str(raw_path or "").strip()
        if not normalized_path:
            return None
        try:
            return self.workspace.resolve_directory(normalized_path, workspace_root=workspace_root)
        except ValueError:
            return None
