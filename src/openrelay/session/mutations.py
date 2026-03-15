from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openrelay.core import AppConfig, DirectoryShortcut, SessionRecord, get_release_workspace
from openrelay.storage import StateStore

from .ux import SessionUX


@dataclass(slots=True)
class SessionMutationService:
    config: AppConfig
    store: StateStore
    session_ux: SessionUX

    def __init__(self, config: AppConfig, store: StateStore, session_ux: SessionUX) -> None:
        self.config = config
        self.store = store
        self.session_ux = session_ux

    def create_named_session(self, scope_key: str, current: SessionRecord, label: str) -> SessionRecord:
        return self.store.create_next_session(scope_key, current, label)

    def clear_context(self, scope_key: str, current: SessionRecord) -> SessionRecord:
        next_session = self.store.create_next_session(scope_key, current, current.label)
        next_session.model_override = current.model_override
        next_session.safety_mode = current.safety_mode
        next_session.release_channel = current.release_channel
        return self.store.save_session(next_session)

    def switch_model(self, scope_key: str, current: SessionRecord, model_override: str) -> SessionRecord:
        next_session = self.store.create_next_session(scope_key, current, current.label)
        next_session.model_override = model_override
        return self.store.save_session(next_session)

    def switch_sandbox(self, scope_key: str, current: SessionRecord, safety_mode: str) -> SessionRecord:
        next_session = self.store.create_next_session(scope_key, current, current.label)
        next_session.safety_mode = safety_mode
        return self.store.save_session(next_session)

    def switch_backend(self, scope_key: str, current: SessionRecord, backend: str) -> SessionRecord:
        next_session = self.store.create_next_session(scope_key, current, current.label)
        next_session.backend = backend
        next_session.native_session_id = ""
        return self.store.save_session(next_session)

    def switch_cwd(self, scope_key: str, current: SessionRecord, cwd: Path) -> SessionRecord:
        next_session = self.store.create_next_session(scope_key, current, current.label)
        next_session.cwd = str(cwd)
        next_session.native_session_id = ""
        return self.store.save_session(next_session)

    def switch_release_channel(self, scope_key: str, current: SessionRecord, channel: str, label: str) -> SessionRecord:
        next_session = self.store.create_next_session(scope_key, current, label)
        next_session.release_channel = channel
        next_session.cwd = str(get_release_workspace(self.config, channel))
        next_session.native_session_id = ""
        if channel == "main":
            next_session.safety_mode = "read-only"
        return self.store.save_session(next_session)

    def reset_scope(self, scope_key: str) -> SessionRecord:
        self.store.clear_sessions(scope_key)
        return self.store.load_session(scope_key)

    def save_directory_shortcut(self, shortcut: DirectoryShortcut) -> DirectoryShortcut:
        return self.store.save_directory_shortcut(shortcut)

    def remove_directory_shortcut(self, name: str) -> bool:
        return self.store.remove_directory_shortcut(name)
