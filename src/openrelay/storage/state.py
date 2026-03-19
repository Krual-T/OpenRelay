from __future__ import annotations

import hashlib

from openrelay.core import AppConfig, DirectoryShortcut, SessionRecord, SessionSummary
from openrelay.observability import MessageEventStore, MessageTraceRecorder, TraceQueryService
from openrelay.session.defaults import SessionDefaultsPolicy
from openrelay.session.store import SessionBindingStore

from .db import DB_FILENAME, LEGACY_DB_FILENAME, SqliteStateContext
from .repositories import (
    SqliteDirectoryShortcutRepository,
    SqliteMessageDedupRepository,
    SqliteMessageRepository,
    SqliteRelaySessionRepository,
    SqliteSessionAliasRepository,
)


class StateStore:
    def __init__(self, config: AppConfig):
        self.config = config
        self.context = SqliteStateContext.open(config)
        self.db_path = self.context.db_path
        self.connection = self.context.connection
        self.defaults = SessionDefaultsPolicy(config)
        self.directory_shortcuts = SqliteDirectoryShortcutRepository(self.context)
        self.session_aliases = SqliteSessionAliasRepository(self.context)
        self.message_dedup = SqliteMessageDedupRepository(self.context)
        self.messages = SqliteMessageRepository(self.context, max_session_messages=config.max_session_messages)
        self.message_event_store = MessageEventStore(self.context.connection)
        self.message_event_store.init_schema()
        self.trace_recorder = MessageTraceRecorder(self.message_event_store)
        self.trace_query = TraceQueryService(self.message_event_store)
        self.bindings = SessionBindingStore(self.context)
        self.sessions = SqliteRelaySessionRepository(
            self.context,
            defaults=self.defaults,
            messages=self.messages,
            bindings=self.bindings,
        )

    def close(self) -> None:
        self.context.close()

    def list_directory_shortcuts(self) -> tuple[DirectoryShortcut, ...]:
        return self.directory_shortcuts.list()

    def save_directory_shortcut(self, shortcut: DirectoryShortcut) -> DirectoryShortcut:
        return self.directory_shortcuts.save(shortcut)

    def get_directory_shortcut(self, name: str) -> DirectoryShortcut | None:
        return self.directory_shortcuts.get(name)

    def remove_directory_shortcut(self, name: str) -> bool:
        return self.directory_shortcuts.remove(name)

    def count_messages(self, session_id: str) -> int:
        return self.messages.count(session_id)

    def find_session_key_alias(self, alias_key: str) -> str | None:
        return self.session_aliases.find(alias_key)

    def save_session_key_alias(self, alias_key: str, base_key: str) -> None:
        self.session_aliases.save(alias_key, base_key)

    def has_session_scope(self, base_key: str) -> bool:
        return self.sessions.has_scope(base_key)

    def owner_session_key(self, base_key: str) -> str:
        return self.sessions.owner_scope(base_key)

    def find_session(self, base_key: str) -> SessionRecord | None:
        return self.sessions.find_active(base_key)

    def bind_scope(self, base_key: str, session_id: str) -> None:
        self.sessions.bind_scope(base_key, session_id)

    def remember_message(self, message_id: str) -> bool:
        return self.message_dedup.remember(message_id)

    def load_session(self, base_key: str, template: SessionRecord | None = None) -> SessionRecord:
        return self.sessions.load_for_scope(base_key, template=template)

    def get_session(self, session_id: str) -> SessionRecord:
        return self.sessions.get(session_id)

    def save_session(self, session: SessionRecord) -> SessionRecord:
        return self.sessions.save(session)

    def save_scope_session(self, scope_key: str, session: SessionRecord) -> SessionRecord:
        return self.sessions.save_scope(scope_key, session)

    def clear_session_messages(self, session_id: str) -> None:
        self.messages.clear(session_id)

    def append_message(self, session_id: str, role: str, content: str) -> None:
        self.messages.append(session_id, role, content)

    def list_messages(self, session_id: str) -> list[dict[str, str]]:
        return self.messages.list(session_id)

    def create_next_session(self, base_key: str, current: SessionRecord | None, label: str = "", **overrides: str) -> SessionRecord:
        return self.sessions.create_next(base_key, current=current, label=label, **overrides)

    def list_sessions(self, base_key: str, limit: int = 20) -> list[SessionSummary]:
        return self.sessions.list_by_scope(base_key, limit=limit)

    def resume_session(self, base_key: str, target: str) -> SessionRecord | None:
        return self.sessions.resume(base_key, target)

    def clear_sessions(self, base_key: str) -> None:
        self.sessions.clear_scope(base_key)


def hash_key(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()
