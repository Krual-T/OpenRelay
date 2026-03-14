from __future__ import annotations

from openrelay.core import AppConfig, SessionRecord, get_release_workspace
from openrelay.storage import StateStore


class SessionLifecycleResolver:
    def __init__(self, config: AppConfig, store: StateStore) -> None:
        self.config = config
        self.store = store

    def load_for_message(
        self,
        session_key: str,
        *,
        is_top_level_control_command: bool,
        is_top_level_message: bool,
        control_key: str,
    ) -> SessionRecord:
        if is_top_level_control_command:
            return self._load_control_session(session_key)
        if self.store.has_session_scope(session_key):
            return self.store.load_session(session_key)
        if is_top_level_message:
            template = self.store.find_session(control_key)
            return self.store.create_next_session(session_key, template)
        template = self.store.find_session(control_key) if session_key != control_key else None
        return self.store.load_session(session_key, template=template)

    def _load_control_session(self, session_key: str) -> SessionRecord:
        current = self.store.find_session(session_key)
        visible = self._find_visible_control_session(session_key)
        if current is not None:
            if visible is not None and self._is_placeholder_control_session(current, session_key):
                return visible
            return current
        if visible is not None:
            return visible
        return self.store.load_session(session_key)

    def _find_visible_control_session(self, session_key: str) -> SessionRecord | None:
        for summary in self.store.list_sessions(session_key, limit=50):
            if summary.base_key == session_key and summary.message_count == 0 and not summary.native_session_id:
                continue
            return self.store.get_session(summary.session_id)
        return None

    def _is_placeholder_control_session(self, session: SessionRecord, session_key: str) -> bool:
        if session.base_key != session_key or session.native_session_id:
            return False
        if self.store.list_messages(session.session_id):
            return False
        release_channel = session.release_channel or "main"
        return (
            session.label == ""
            and session.backend == self.config.backend.default_backend
            and session.cwd == str(get_release_workspace(self.config, release_channel))
            and session.model_override == self.config.backend.default_model
            and session.safety_mode == self.config.backend.default_safety_mode
            and release_channel == "main"
        )
