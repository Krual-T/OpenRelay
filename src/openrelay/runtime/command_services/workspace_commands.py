from __future__ import annotations

import shlex

from openrelay.core import DirectoryShortcut, IncomingMessage, SessionRecord
from openrelay.session import SessionMutationService, SessionShortcutService, SessionWorkspaceService

from ..command_context import PanelCommandArgs


class WorkspaceCommandService:
    def __init__(
        self,
        workspace: SessionWorkspaceService,
        shortcuts: SessionShortcutService,
        session_mutations: SessionMutationService,
    ) -> None:
        self.workspace = workspace
        self.shortcuts = shortcuts
        self.session_mutations = session_mutations

    def resolve_workspace_browser_path(self, raw_path: str, session: SessionRecord):
        return self.workspace.resolve_workspace_browser_path(raw_path, session)

    def resolve_workspace_selection(self, raw_path: str, session: SessionRecord):
        return self.workspace.resolve_workspace_selection(raw_path, session)

    def switch_workspace_directory(self, session_key: str, session: SessionRecord, raw_path: str) -> SessionRecord:
        next_cwd = self.resolve_workspace_selection(raw_path, session)
        return self.session_mutations.switch_cwd(session_key, session, next_cwd)

    def format_workspace_switch_success(self, session: SessionRecord) -> str:
        return "\n".join([
            f"工作区已切换到 {self.workspace.format_cwd(session.cwd, session)}。",
            "现在直接发消息，就会在这个目录进入 Codex。",
            "当前 scope 已原地更新；如需切回旧 thread，请用 /resume。",
        ])

    def build_directory_shortcut_entries(self, session: SessionRecord, limit: int = 100):
        return self.shortcuts.build_directory_shortcut_entries(session, limit=limit)

    def save_directory_shortcut(self, shortcut: DirectoryShortcut) -> None:
        self.session_mutations.save_directory_shortcut(shortcut)

    def remove_directory_shortcut(self, name: str) -> bool:
        return self.session_mutations.remove_directory_shortcut(name)

    def resolve_directory_shortcut(self, name: str, session: SessionRecord):
        return self.shortcuts.resolve_directory_shortcut(name, session)

    def parse_shortcut_add(self, tokens: list[str]) -> DirectoryShortcut:
        if len(tokens) < 2:
            raise ValueError("add 需要 <name> <path>")
        name = tokens[0].strip()
        path = tokens[1].strip()
        if not name:
            raise ValueError("name 不能为空")
        if not path:
            raise ValueError("path 不能为空")
        channels: tuple[str, ...] = ("all",)
        if len(tokens) >= 3:
            channel = tokens[2].strip().lower()
            if channel not in {"all", "main", "develop"}:
                raise ValueError("channels 仅支持 all / main / develop")
            channels = (channel,)
        if len(tokens) > 3:
            raise ValueError("add 最多支持一个 channels 参数")
        return DirectoryShortcut(name=name, path=path, channels=channels)
