from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from openrelay.config import AppConfig
from openrelay.models import SessionRecord, SessionSummary
from openrelay.native_sessions import NativeSessionSummary, find_native_session, import_native_session, list_native_sessions
from openrelay.state import StateStore


SESSION_SORT_ACTIVE = "active-first"
SESSION_SORT_UPDATED = "updated-desc"
SESSION_SORT_MODES = {SESSION_SORT_ACTIVE, SESSION_SORT_UPDATED}
SessionSortMode = Literal["active-first", "updated-desc"]


@dataclass(slots=True)
class SessionListEntry:
    session_id: str
    resume_token: str
    native_session_id: str
    label: str
    updated_at: str
    active: bool
    origin: str
    release_channel: str
    cwd: str
    first_user_message: str
    last_assistant_message: str
    message_count: int
    matches_workspace: bool

    @property
    def dedup_key(self) -> str:
        return self.native_session_id or self.session_id


@dataclass(slots=True)
class SessionResumeResult:
    session: SessionRecord
    imported: bool
    entry: SessionListEntry | None


class SessionBrowser:
    def __init__(self, config: AppConfig, store: StateStore):
        self.config = config
        self.store = store

    def list_entries(
        self,
        session_key: str,
        session: SessionRecord,
        limit: int = 12,
        sort_mode: SessionSortMode = SESSION_SORT_ACTIVE,
    ) -> list[SessionListEntry]:
        local_sessions = self.store.list_sessions(session_key, limit=limit)
        merged: list[SessionListEntry] = []
        seen: set[str] = set()

        for entry in local_sessions:
            item = self._local_entry(entry)
            seen.add(item.dedup_key)
            merged.append(item)

        for native in self.list_importable_native_sessions(local_sessions, session, limit):
            item = self._native_entry(native)
            if item.dedup_key in seen:
                continue
            seen.add(item.dedup_key)
            merged.append(item)

        self._sort_entries(merged, sort_mode)
        return merged[:limit]

    def resume(
        self,
        session_key: str,
        session: SessionRecord,
        target: str,
        entries: list[SessionListEntry],
    ) -> SessionResumeResult | None:
        resolved_target = self.resolve_target(target, entries)
        local_match = self.find_local_session(session_key, resolved_target)
        if local_match is not None:
            resumed = self.store.resume_session(session_key, local_match.session_id)
            if resumed is None:
                return None
            return SessionResumeResult(
                session=resumed,
                imported=False,
                entry=self.find_entry(entries, resumed.session_id, local_match.native_session_id),
            )

        if not resolved_target or resolved_target.lower() in {"latest", "prev", "previous"}:
            latest_native = self.list_importable_native_sessions(self.store.list_sessions(session_key, limit=50), session, 1)
            if not latest_native:
                return None
            native = latest_native[0]
            imported = import_native_session(self.store, session_key, native, session)
            return SessionResumeResult(
                session=imported,
                imported=True,
                entry=self.find_entry(entries, native.session_id, native.session_id),
            )

        native = find_native_session(self.config, resolved_target)
        if native is None:
            entry = self.find_entry(entries, resolved_target, resolved_target)
            if entry is None:
                return None
            native = find_native_session(self.config, entry.native_session_id or entry.session_id)
            if native is None:
                return None

        imported = import_native_session(self.store, session_key, native, session)
        return SessionResumeResult(
            session=imported,
            imported=True,
            entry=self.find_entry(entries, native.session_id, native.session_id),
        )

    def resolve_target(self, target: str, entries: list[SessionListEntry]) -> str:
        normalized = target.strip()
        if not normalized.isdigit():
            return normalized
        index = int(normalized) - 1
        if 0 <= index < len(entries):
            return entries[index].resume_token
        return normalized

    def find_entry(self, entries: list[SessionListEntry], token: str, native_token: str = "") -> SessionListEntry | None:
        native_match = native_token.strip()
        for entry in entries:
            if token and token in {entry.resume_token, entry.session_id, entry.native_session_id}:
                return entry
            if native_match and native_match in {entry.native_session_id, entry.resume_token, entry.session_id}:
                return entry
        return None

    def find_local_session(self, session_key: str, token: str) -> SessionSummary | None:
        normalized = token.strip()
        if not normalized:
            return None
        for entry in self.store.list_sessions(session_key, limit=50):
            if normalized in {entry.session_id, entry.native_session_id}:
                return entry
        return None

    def list_importable_native_sessions(self, local_sessions: list[SessionSummary], session: SessionRecord, limit: int = 10) -> list[NativeSessionSummary]:
        if session.backend != "codex":
            return []
        known_ids = {entry.native_session_id or entry.session_id for entry in local_sessions}
        return [entry for entry in list_native_sessions(self.config, limit=limit) if entry.session_id not in known_ids]

    def _local_entry(self, entry: SessionSummary) -> SessionListEntry:
        return SessionListEntry(
            session_id=entry.session_id,
            resume_token=entry.session_id,
            native_session_id=entry.native_session_id or "",
            label=entry.label,
            updated_at=entry.updated_at,
            active=entry.active,
            origin="local",
            release_channel=entry.release_channel,
            cwd=entry.cwd,
            first_user_message=entry.first_user_message,
            last_assistant_message=entry.last_assistant_message,
            message_count=entry.message_count,
            matches_workspace=True,
        )

    def _native_entry(self, entry: NativeSessionSummary) -> SessionListEntry:
        return SessionListEntry(
            session_id=entry.session_id,
            resume_token=entry.session_id,
            native_session_id=entry.session_id,
            label=entry.label,
            updated_at=entry.updated_at,
            active=False,
            origin="native",
            release_channel=entry.release_channel,
            cwd=entry.cwd,
            first_user_message=entry.first_user_message,
            last_assistant_message="",
            message_count=0,
            matches_workspace=entry.matches_workspace,
        )

    def _sort_entries(self, entries: list[SessionListEntry], sort_mode: SessionSortMode) -> None:
        if sort_mode not in SESSION_SORT_MODES:
            raise ValueError(f"unsupported session sort mode: {sort_mode}")
        entries.sort(key=lambda entry: (entry.updated_at, entry.matches_workspace), reverse=True)
        if sort_mode == SESSION_SORT_ACTIVE:
            entries.sort(key=lambda entry: not entry.active)
