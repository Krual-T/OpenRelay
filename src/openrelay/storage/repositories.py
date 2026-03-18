from __future__ import annotations

from dataclasses import asdict, replace
import json
import sqlite3
import time
import uuid

from openrelay.core import DirectoryShortcut, SessionRecord, SessionSummary, infer_release_channel, utc_now
from openrelay.session.defaults import SessionDefaultsPolicy
from openrelay.session.repositories import SessionBindingRepository

from .db import SqliteStateContext

DEDUP_TTL_SECONDS = 48 * 60 * 60


class SqliteDirectoryShortcutRepository:
    def __init__(self, context: SqliteStateContext) -> None:
        self.context = context

    @property
    def connection(self) -> sqlite3.Connection:
        return self.context.connection

    def list(self) -> tuple[DirectoryShortcut, ...]:
        rows = self.connection.execute(
            "SELECT name, path, channels_json FROM directory_shortcuts ORDER BY name COLLATE NOCASE ASC"
        ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def get(self, name: str) -> DirectoryShortcut | None:
        row = self.connection.execute(
            "SELECT name, path, channels_json FROM directory_shortcuts WHERE name = ? COLLATE NOCASE",
            (name.strip(),),
        ).fetchone()
        if row is None:
            return None
        return self._from_row(row)

    def save(self, shortcut: DirectoryShortcut) -> DirectoryShortcut:
        now = utc_now()
        self.connection.execute(
            """
            INSERT INTO directory_shortcuts(name, path, channels_json, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
              path = excluded.path,
              channels_json = excluded.channels_json,
              updated_at = excluded.updated_at
            """,
            (
                shortcut.name.strip(),
                shortcut.path.strip(),
                json.dumps(list(shortcut.channels or ("all",)), ensure_ascii=False),
                now,
                now,
            ),
        )
        self.connection.commit()
        return self.get(shortcut.name) or shortcut

    def remove(self, name: str) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM directory_shortcuts WHERE name = ? COLLATE NOCASE",
            (name.strip(),),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def _from_row(self, row: sqlite3.Row) -> DirectoryShortcut:
        return DirectoryShortcut(
            name=str(row["name"] or "").strip(),
            path=str(row["path"] or "").strip(),
            channels=self._normalize_channels(str(row["channels_json"] or "")),
        )

    def _normalize_channels(self, raw_channels: str) -> tuple[str, ...]:
        try:
            payload = json.loads(raw_channels or "[]")
        except json.JSONDecodeError:
            payload = []
        channels = tuple(
            token
            for token in (str(item).strip().lower() for item in payload if str(item).strip())
            if token in {"all", "main", "develop"}
        )
        return channels or ("all",)


class SqliteSessionAliasRepository:
    def __init__(self, context: SqliteStateContext) -> None:
        self.context = context

    @property
    def connection(self) -> sqlite3.Connection:
        return self.context.connection

    def find(self, alias_key: str) -> str | None:
        row = self.connection.execute(
            "SELECT base_key FROM session_key_aliases WHERE alias_key = ?",
            (alias_key.strip(),),
        ).fetchone()
        if row is None:
            return None
        return str(row["base_key"] or "").strip() or None

    def save(self, alias_key: str, base_key: str) -> None:
        alias = alias_key.strip()
        base = base_key.strip()
        if not alias or not base or alias == base:
            return
        now = utc_now()
        self.connection.execute(
            """
            INSERT INTO session_key_aliases(alias_key, base_key, created_at, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(alias_key) DO UPDATE SET
              base_key = excluded.base_key,
              updated_at = excluded.updated_at
            """,
            (alias, base, now, now),
        )
        self.connection.commit()


class SqliteMessageDedupRepository:
    def __init__(self, context: SqliteStateContext) -> None:
        self.context = context

    @property
    def connection(self) -> sqlite3.Connection:
        return self.context.connection

    def remember(self, message_id: str) -> bool:
        now = int(time.time())
        cutoff = now - DEDUP_TTL_SECONDS
        self.connection.execute("DELETE FROM dedup WHERE seen_at < ?", (cutoff,))
        row = self.connection.execute(
            "SELECT seen_at FROM dedup WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        duplicate = row is not None and int(row["seen_at"] or 0) >= cutoff
        self.connection.execute(
            "INSERT INTO dedup(message_id, seen_at) VALUES(?, ?) ON CONFLICT(message_id) DO UPDATE SET seen_at = excluded.seen_at",
            (message_id, now),
        )
        self.connection.commit()
        return duplicate


class SqliteMessageRepository:
    def __init__(self, context: SqliteStateContext, *, max_session_messages: int) -> None:
        self.context = context
        self.max_session_messages = max(max_session_messages, 1)

    @property
    def connection(self) -> sqlite3.Connection:
        return self.context.connection

    def append(self, session_id: str, role: str, content: str) -> None:
        self.connection.execute(
            "INSERT INTO messages(session_id, role, content, created_at) VALUES(?, ?, ?, ?)",
            (session_id, role, content, utc_now()),
        )
        self._truncate(session_id)
        self.connection.commit()

    def list(self, session_id: str) -> list[dict[str, str]]:
        rows = self.connection.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        return [{"role": str(row["role"]), "content": str(row["content"])} for row in rows]

    def clear(self, session_id: str) -> None:
        self.connection.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self.connection.commit()

    def count(self, session_id: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["count"] or 0)

    def first(self, session_id: str, role: str) -> str:
        row = self.connection.execute(
            "SELECT content FROM messages WHERE session_id = ? AND role = ? ORDER BY id ASC LIMIT 1",
            (session_id, role),
        ).fetchone()
        return str((row["content"] if row else "") or "")

    def last(self, session_id: str, role: str) -> str:
        row = self.connection.execute(
            "SELECT content FROM messages WHERE session_id = ? AND role = ? ORDER BY id DESC LIMIT 1",
            (session_id, role),
        ).fetchone()
        return str((row["content"] if row else "") or "")

    def _truncate(self, session_id: str) -> None:
        count = self.count(session_id)
        if count <= self.max_session_messages:
            return
        extra = count - self.max_session_messages
        self.connection.execute(
            "DELETE FROM messages WHERE id IN (SELECT id FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT ?)",
            (session_id, extra),
        )


class SqliteRelaySessionRepository:
    def __init__(
        self,
        context: SqliteStateContext,
        defaults: SessionDefaultsPolicy,
        messages: SqliteMessageRepository,
        bindings: SessionBindingRepository | None = None,
    ) -> None:
        self.context = context
        self.defaults = defaults
        self.messages = messages
        self.bindings = bindings

    @property
    def connection(self) -> sqlite3.Connection:
        return self.context.connection

    def get(self, session_id: str) -> SessionRecord:
        row = self.connection.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown session: {session_id}")
        return self._hydrate_record(self._record_from_row(row))

    def find(self, session_id: str) -> SessionRecord | None:
        try:
            return self.get(session_id)
        except KeyError:
            return None

    def find_active(self, base_key: str) -> SessionRecord | None:
        row = self.connection.execute(
            "SELECT active_session_id FROM session_pointers WHERE base_key = ?",
            (base_key,),
        ).fetchone()
        if row is None:
            return None
        return self.find(str(row["active_session_id"] or ""))

    def has_scope(self, base_key: str) -> bool:
        key = base_key.strip()
        if not key:
            return False
        pointer = self.connection.execute(
            "SELECT 1 FROM session_pointers WHERE base_key = ? LIMIT 1",
            (key,),
        ).fetchone()
        if pointer is not None:
            return True
        row = self.connection.execute(
            "SELECT 1 FROM sessions WHERE base_key = ? LIMIT 1",
            (key,),
        ).fetchone()
        return row is not None

    def owner_scope(self, base_key: str) -> str:
        key = base_key.strip()
        if ":thread:" not in key:
            return key
        prefix, suffix = key.split(":thread:", 1)
        if ":sender:" in suffix:
            _thread_id, sender_suffix = suffix.split(":sender:", 1)
            return f"{prefix}:sender:{sender_suffix}"
        return prefix

    def bind_scope(self, base_key: str, session_id: str) -> None:
        scope_key = base_key.strip()
        target_session_id = session_id.strip()
        if not scope_key or not target_session_id:
            return
        self.connection.execute(
            """
            INSERT INTO session_pointers(base_key, active_session_id, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(base_key) DO UPDATE SET active_session_id = excluded.active_session_id, updated_at = excluded.updated_at
            """,
            (scope_key, target_session_id, utc_now()),
        )
        self.connection.commit()

    def load_for_scope(self, base_key: str, template: SessionRecord | None = None) -> SessionRecord:
        requested_key = base_key.strip()
        existing = self.find_active(requested_key)
        if existing is not None:
            return existing
        owner_key = self.owner_scope(requested_key)
        if owner_key != requested_key:
            owner_session = self.find_active(owner_key)
            if owner_session is not None:
                self.bind_scope(requested_key, owner_session.session_id)
                return owner_session
        release_channel = self.defaults.resolve_release_channel(template)
        session = SessionRecord(
            session_id=self._new_session_id(),
            base_key=owner_key,
            backend=template.backend if template else self.defaults.default_backend(),
            cwd=template.cwd if template else self.defaults.default_workspace(release_channel),
            label=template.label if template else "",
            model_override=template.model_override if template else self.defaults.default_model(),
            safety_mode=template.safety_mode if template else self.defaults.default_safety_mode(),
            native_session_id="",
            release_channel=release_channel,
            last_usage={},
        )
        saved = self.save(session)
        if requested_key != owner_key:
            self.bind_scope(requested_key, saved.session_id)
        return saved

    def create_next(self, base_key: str, current: SessionRecord | None = None, label: str = "", **overrides: str) -> SessionRecord:
        requested_key = base_key.strip()
        owner_key = self.owner_scope(requested_key)
        release_channel = self.defaults.resolve_release_channel(current, requested=str(overrides.get("release_channel") or ""))
        session = SessionRecord(
            session_id=self._new_session_id(),
            base_key=owner_key,
            backend=str(overrides.get("backend") or (current.backend if current else self.defaults.default_backend())),
            cwd=str(overrides.get("cwd") or (current.cwd if current else self.defaults.default_workspace(release_channel))),
            label=label.strip(),
            model_override=(
                str(overrides["model_override"])
                if "model_override" in overrides and overrides.get("model_override") is not None
                else (current.model_override if current else self.defaults.default_model())
            ),
            safety_mode=str(overrides.get("safety_mode") or (current.safety_mode if current else self.defaults.default_safety_mode())),
            native_session_id="",
            release_channel=release_channel,
            last_usage={},
        )
        saved = self.save(session)
        if requested_key != owner_key:
            self.bind_scope(requested_key, saved.session_id)
        return saved

    def save(self, session: SessionRecord) -> SessionRecord:
        now = utc_now()
        payload = asdict(session)
        payload["base_key"] = self.owner_scope(str(payload.get("base_key") or ""))
        payload["updated_at"] = now
        if not payload["created_at"]:
            payload["created_at"] = now
        if not payload.get("release_channel"):
            payload["release_channel"] = infer_release_channel(self.context.config, session)
        payload["last_usage_json"] = json.dumps(payload.pop("last_usage", {}) or {}, ensure_ascii=False)
        self.connection.execute(
            """
            INSERT INTO sessions(session_id, base_key, backend, cwd, label, model_override, safety_mode, native_session_id, release_channel, last_usage_json, created_at, updated_at)
            VALUES(:session_id, :base_key, :backend, :cwd, :label, :model_override, :safety_mode, :native_session_id, :release_channel, :last_usage_json, :created_at, :updated_at)
            ON CONFLICT(session_id) DO UPDATE SET
              backend = excluded.backend,
              cwd = excluded.cwd,
              label = excluded.label,
              model_override = excluded.model_override,
              safety_mode = excluded.safety_mode,
              native_session_id = excluded.native_session_id,
              release_channel = excluded.release_channel,
              last_usage_json = excluded.last_usage_json,
              updated_at = excluded.updated_at
            """,
            payload,
        )
        self.connection.execute(
            """
            INSERT INTO session_pointers(base_key, active_session_id, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(base_key) DO UPDATE SET active_session_id = excluded.active_session_id, updated_at = excluded.updated_at
            """,
            (payload["base_key"], session.session_id, now),
        )
        self.connection.commit()
        return self.get(session.session_id)

    def save_scope(self, base_key: str, session: SessionRecord) -> SessionRecord:
        requested_key = base_key.strip()
        saved = self.save(session)
        if requested_key and requested_key != saved.base_key:
            self.bind_scope(requested_key, saved.session_id)
        return saved

    def list_by_scope(self, base_key: str, limit: int = 20) -> list[SessionSummary]:
        owner_key = self.owner_scope(base_key)
        if not owner_key:
            return []
        pointer = self.connection.execute(
            "SELECT active_session_id FROM session_pointers WHERE base_key = ?",
            (owner_key,),
        ).fetchone()
        active_id = str(pointer["active_session_id"] or "") if pointer else ""
        rows = self.connection.execute(
            "SELECT * FROM sessions WHERE base_key = ? ORDER BY updated_at DESC LIMIT ?",
            (owner_key, max(limit * 10, 50)),
        ).fetchall()
        summaries: list[SessionSummary] = []
        for row in rows:
            session_id = str(row["session_id"] or "")
            summary = SessionSummary(
                session_id=session_id,
                base_key=str(row["base_key"] or ""),
                backend=str(row["backend"] or ""),
                label=str(row["label"] or ""),
                cwd=str(row["cwd"] or ""),
                native_session_id=str(row["native_session_id"] or ""),
                updated_at=str(row["updated_at"] or ""),
                active=session_id == active_id,
                release_channel=str(row["release_channel"] or "main") or "main",
                first_user_message=self.messages.first(session_id, "user"),
                last_assistant_message=self.messages.last(session_id, "assistant"),
                message_count=self.messages.count(session_id),
            )
            summaries.append(self._hydrate_summary(summary))
        summaries.sort(key=lambda entry: (entry.active, entry.updated_at), reverse=True)
        return summaries[:limit]

    def resume(self, base_key: str, target: str) -> SessionRecord | None:
        requested_key = base_key.strip()
        owner_key = self.owner_scope(requested_key)
        normalized_target = target.strip()
        pointer = self.connection.execute(
            "SELECT active_session_id FROM session_pointers WHERE base_key = ?",
            (owner_key,),
        ).fetchone()
        active_id = str(pointer["active_session_id"] or "") if pointer else ""
        sessions = self.list_by_scope(owner_key, limit=50)
        if not normalized_target or normalized_target in {"latest", "prev", "previous"}:
            chosen = next((entry for entry in sessions if entry.session_id != active_id), None)
        else:
            chosen = next((entry for entry in sessions if entry.session_id == normalized_target), None)
        if chosen is None:
            return None
        self.connection.execute(
            "UPDATE session_pointers SET active_session_id = ?, updated_at = ? WHERE base_key = ?",
            (chosen.session_id, utc_now(), owner_key),
        )
        self.connection.commit()
        if requested_key and requested_key != owner_key:
            self.bind_scope(requested_key, chosen.session_id)
        return self.get(chosen.session_id)

    def clear_scope(self, base_key: str) -> None:
        owner_key = self.owner_scope(base_key)
        rows = self.connection.execute("SELECT session_id FROM sessions WHERE base_key = ?", (owner_key,)).fetchall()
        session_ids = [str(row["session_id"] or "") for row in rows]
        self.connection.execute("DELETE FROM sessions WHERE base_key = ?", (owner_key,))
        patterns = self._scope_patterns(owner_key)
        if patterns:
            where_clause = " OR ".join("base_key LIKE ?" if "%" in pattern else "base_key = ?" for pattern in patterns)
            self.connection.execute(f"DELETE FROM session_pointers WHERE {where_clause}", patterns)
        if session_ids:
            self.connection.executemany("DELETE FROM messages WHERE session_id = ?", [(session_id,) for session_id in session_ids])
            clear_many = getattr(self.bindings, "clear_many", None)
            if callable(clear_many):
                clear_many(session_ids)
        self.connection.commit()

    def _record_from_row(self, row: sqlite3.Row) -> SessionRecord:
        payload = dict(row)
        try:
            payload["last_usage"] = json.loads(payload.pop("last_usage_json", "{}") or "{}")
        except json.JSONDecodeError:
            payload["last_usage"] = {}
        record = SessionRecord(**payload)
        if not record.release_channel:
            record.release_channel = infer_release_channel(self.context.config, record)
        return record

    def _hydrate_record(self, session: SessionRecord) -> SessionRecord:
        binding = self.bindings.get(session.session_id) if self.bindings is not None else None
        if binding is None:
            return session
        return replace(
            session,
            backend=binding.backend,
            cwd=binding.cwd,
            model_override=binding.model,
            safety_mode=binding.safety_mode,
            native_session_id=binding.native_session_id,
        )

    def _hydrate_summary(self, summary: SessionSummary) -> SessionSummary:
        binding = self.bindings.get(summary.session_id) if self.bindings is not None else None
        if binding is None:
            return summary
        return replace(
            summary,
            backend=binding.backend,
            cwd=binding.cwd,
            native_session_id=binding.native_session_id,
        )

    def _scope_patterns(self, owner_key: str) -> list[str]:
        if ":thread:" in owner_key:
            return [owner_key]
        return [f"{owner_key}:thread:%", owner_key]

    def _new_session_id(self) -> str:
        return f"s_{uuid.uuid4().hex[:12]}"
