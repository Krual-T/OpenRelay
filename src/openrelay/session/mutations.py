from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path

from openrelay.core import AppConfig, DirectoryShortcut, SessionRecord, get_release_workspace
from openrelay.presentation.session import SessionPresentation
from openrelay.storage import StateStore

from .models import RelaySessionBinding
from .store import SessionBindingStore


@dataclass(slots=True)
class SessionMutationService:
    config: AppConfig
    store: StateStore
    session_ux: SessionPresentation

    def __init__(self, config: AppConfig, store: StateStore, session_ux: SessionPresentation) -> None:
        self.config = config
        self.store = store
        self.session_ux = session_ux
        self.bindings = SessionBindingStore(store)

    def create_named_session(self, scope_key: str, current: SessionRecord, label: str) -> SessionRecord:
        return self.store.create_next_session(scope_key, current, label)

    def clear_context(self, scope_key: str, current: SessionRecord) -> SessionRecord:
        return self._update_scope_session(
            scope_key,
            current,
            native_session_id="",
            last_usage={},
            clear_messages=True,
        )

    def switch_model(self, scope_key: str, current: SessionRecord, model_override: str) -> SessionRecord:
        return self._update_scope_session(
            scope_key,
            current,
            model_override=model_override,
            native_session_id="",
            last_usage={},
            clear_messages=True,
        )

    def switch_sandbox(self, scope_key: str, current: SessionRecord, safety_mode: str) -> SessionRecord:
        return self._update_scope_session(
            scope_key,
            current,
            safety_mode=safety_mode,
            native_session_id="",
            last_usage={},
            clear_messages=True,
        )

    def switch_backend(self, scope_key: str, current: SessionRecord, backend: str) -> SessionRecord:
        return self._update_scope_session(
            scope_key,
            current,
            backend=backend,
            native_session_id="",
            last_usage={},
            clear_messages=True,
        )

    def switch_cwd(self, scope_key: str, current: SessionRecord, cwd: Path) -> SessionRecord:
        return self._update_scope_session(
            scope_key,
            current,
            cwd=str(cwd),
            native_session_id="",
            last_usage={},
            clear_messages=True,
        )

    def switch_release_channel(self, scope_key: str, current: SessionRecord, channel: str, label: str) -> SessionRecord:
        updates: dict[str, object] = {
            "label": label,
            "release_channel": channel,
            "cwd": str(get_release_workspace(self.config, channel)),
            "native_session_id": "",
            "last_usage": {},
        }
        if channel == "main":
            updates["safety_mode"] = "read-only"
        return self._update_scope_session(scope_key, current, clear_messages=True, **updates)

    def reset_scope(self, scope_key: str) -> SessionRecord:
        self.store.clear_sessions(scope_key)
        return self.store.load_session(scope_key)

    def bind_native_thread(
        self,
        scope_key: str,
        current: SessionRecord,
        thread_id: str,
        *,
        cwd: str | None = None,
        label: str = "",
    ) -> SessionRecord:
        updates: dict[str, object] = {
            "native_session_id": thread_id.strip(),
            "release_channel": "",
            "last_usage": {},
        }
        if cwd:
            updates["cwd"] = cwd
        if label:
            updates["label"] = label
        return self._update_scope_session(scope_key, current, clear_messages=True, **updates)

    def save_directory_shortcut(self, shortcut: DirectoryShortcut) -> DirectoryShortcut:
        return self.store.save_directory_shortcut(shortcut)

    def remove_directory_shortcut(self, name: str) -> bool:
        return self.store.remove_directory_shortcut(name)

    def _update_scope_session(
        self,
        scope_key: str,
        current: SessionRecord,
        *,
        clear_messages: bool = False,
        **updates: object,
    ) -> SessionRecord:
        next_session = replace(current, **updates)
        saved = self.store.save_scope_session(scope_key, next_session)
        self._save_binding_if_needed(current, saved)
        if clear_messages:
            self.store.clear_session_messages(saved.session_id)
        return self.store.get_session(saved.session_id)

    def _save_binding_if_needed(self, current: SessionRecord, saved: SessionRecord) -> None:
        existing = self.bindings.get(current.session_id)
        if existing is None and not saved.native_session_id:
            return
        if existing is None:
            binding = self._binding_from_session(saved)
        else:
            binding = replace(
                existing,
                relay_session_id=saved.session_id,
                backend=saved.backend,  # type: ignore[arg-type]
                native_session_id=saved.native_session_id,
                cwd=saved.cwd,
                model=saved.model_override,
                safety_mode=saved.safety_mode,
            )
        self.bindings.save(binding)

    def _binding_from_session(self, session: SessionRecord) -> RelaySessionBinding:
        return RelaySessionBinding(
            relay_session_id=session.session_id,
            backend=session.backend,  # type: ignore[arg-type]
            native_session_id=session.native_session_id,
            cwd=session.cwd,
            model=session.model_override,
            safety_mode=session.safety_mode,
            feishu_chat_id="",
            feishu_thread_id="",
            created_at=session.created_at,
            updated_at=session.updated_at,
        )
