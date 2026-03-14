from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid

from openrelay.core import AppConfig, DirectoryShortcut, SessionRecord, SessionSummary, infer_release_channel, utc_now


DEDUP_TTL_SECONDS = 48 * 60 * 60
DB_FILENAME = "openrelay.sqlite3"
LEGACY_DB_FILENAME = "agentmux.sqlite3"


class StateStore:
    def __init__(self, config: AppConfig):
        self.config = config
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self._resolve_db_path()
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def _resolve_db_path(self) -> Path:
        db_path = self.config.data_dir / DB_FILENAME
        legacy_db_path = self.config.data_dir / LEGACY_DB_FILENAME
        if db_path.exists() or not legacy_db_path.exists():
            return db_path
        legacy_db_path.replace(db_path)
        for suffix in ("-shm", "-wal"):
            legacy_sidecar_path = Path(f"{legacy_db_path}{suffix}")
            if legacy_sidecar_path.exists():
                legacy_sidecar_path.replace(Path(f"{db_path}{suffix}"))
        return db_path

    def close(self) -> None:
        self.connection.close()

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS session_pointers (
              base_key TEXT PRIMARY KEY,
              active_session_id TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
              session_id TEXT PRIMARY KEY,
              base_key TEXT NOT NULL,
              backend TEXT NOT NULL,
              cwd TEXT NOT NULL,
              label TEXT NOT NULL DEFAULT '',
              model_override TEXT NOT NULL DEFAULT '',
              safety_mode TEXT NOT NULL,
              native_session_id TEXT NOT NULL DEFAULT '',
              release_channel TEXT NOT NULL DEFAULT 'main',
              last_usage_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_base_key_updated ON sessions(base_key, updated_at DESC);
            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL,
              role TEXT NOT NULL,
              content TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session_id_id ON messages(session_id, id ASC);
            CREATE TABLE IF NOT EXISTS dedup (
              message_id TEXT PRIMARY KEY,
              seen_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS session_key_aliases (
              alias_key TEXT PRIMARY KEY,
              base_key TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_session_key_aliases_base_key ON session_key_aliases(base_key);
            CREATE TABLE IF NOT EXISTS directory_shortcuts (
              name TEXT PRIMARY KEY COLLATE NOCASE,
              path TEXT NOT NULL,
              channels_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(sessions)").fetchall()}
        if "release_channel" not in columns:
            self.connection.execute("ALTER TABLE sessions ADD COLUMN release_channel TEXT NOT NULL DEFAULT 'main'")
        if "last_usage_json" not in columns:
            self.connection.execute("ALTER TABLE sessions ADD COLUMN last_usage_json TEXT NOT NULL DEFAULT '{}'")
        self.connection.commit()

    def list_directory_shortcuts(self) -> tuple[DirectoryShortcut, ...]:
        rows = self.connection.execute(
            "SELECT name, path, channels_json FROM directory_shortcuts ORDER BY name COLLATE NOCASE ASC"
        ).fetchall()
        return tuple(self._directory_shortcut_from_row(row) for row in rows)

    def save_directory_shortcut(self, shortcut: DirectoryShortcut) -> DirectoryShortcut:
        now = utc_now()
        payload = (
            shortcut.name.strip(),
            shortcut.path.strip(),
            json.dumps(list(shortcut.channels or ("all",)), ensure_ascii=False),
            now,
            now,
        )
        self.connection.execute(
            """
            INSERT INTO directory_shortcuts(name, path, channels_json, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
              path = excluded.path,
              channels_json = excluded.channels_json,
              updated_at = excluded.updated_at
            """,
            payload,
        )
        self.connection.commit()
        return self.get_directory_shortcut(shortcut.name) or shortcut

    def get_directory_shortcut(self, name: str) -> DirectoryShortcut | None:
        row = self.connection.execute(
            "SELECT name, path, channels_json FROM directory_shortcuts WHERE name = ? COLLATE NOCASE",
            (name.strip(),),
        ).fetchone()
        if row is None:
            return None
        return self._directory_shortcut_from_row(row)

    def remove_directory_shortcut(self, name: str) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM directory_shortcuts WHERE name = ? COLLATE NOCASE",
            (name.strip(),),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def _directory_shortcut_from_row(self, row: sqlite3.Row) -> DirectoryShortcut:
        return DirectoryShortcut(
            name=str(row["name"] or "").strip(),
            path=str(row["path"] or "").strip(),
            channels=self._normalize_directory_shortcut_channels(row["channels_json"]),
        )

    def _normalize_directory_shortcut_channels(self, raw_channels: str) -> tuple[str, ...]:
        try:
            channels_payload = json.loads(raw_channels or "[]")
        except json.JSONDecodeError:
            channels_payload = []
        channels = tuple(
            token
            for token in (str(item).strip().lower() for item in channels_payload if str(item).strip())
            if token in {"all", "main", "develop"}
        )
        return channels or ("all",)

    def _new_session_id(self) -> str:
        return f"s_{uuid.uuid4().hex[:12]}"

    def _default_cwd(self, release_channel: str = "main") -> str:
        from openrelay.core import get_release_workspace

        return str(get_release_workspace(self.config, release_channel))

    def _default_backend(self) -> str:
        return self.config.backend.default_backend

    def _default_model(self) -> str:
        return self.config.backend.default_model

    def _default_mode(self) -> str:
        return self.config.backend.default_safety_mode

    def _truncate_messages(self, session_id: str) -> None:
        max_messages = self.config.max_session_messages
        count = self.count_messages(session_id)
        if count <= max_messages:
            return
        extra = count - max_messages
        self.connection.execute(
            "DELETE FROM messages WHERE id IN (SELECT id FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT ?)",
            (session_id, extra),
        )

    def _first_message(self, session_id: str, role: str) -> str:
        row = self.connection.execute(
            "SELECT content FROM messages WHERE session_id = ? AND role = ? ORDER BY id ASC LIMIT 1",
            (session_id, role),
        ).fetchone()
        return (row["content"] if row else "") or ""

    def _last_message(self, session_id: str, role: str) -> str:
        row = self.connection.execute(
            "SELECT content FROM messages WHERE session_id = ? AND role = ? ORDER BY id DESC LIMIT 1",
            (session_id, role),
        ).fetchone()
        return (row["content"] if row else "") or ""

    def count_messages(self, session_id: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["count"] or 0)

    def find_session_key_alias(self, alias_key: str) -> str | None:
        row = self.connection.execute(
            "SELECT base_key FROM session_key_aliases WHERE alias_key = ?",
            (alias_key.strip(),),
        ).fetchone()
        if row is None:
            return None
        return str(row["base_key"] or "").strip() or None

    def save_session_key_alias(self, alias_key: str, base_key: str) -> None:
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

    def has_session_scope(self, base_key: str) -> bool:
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

    def owner_session_key(self, base_key: str) -> str:
        key = base_key.strip()
        if ":thread:" not in key:
            return key
        prefix, suffix = key.split(":thread:", 1)
        if ":sender:" in suffix:
            _thread_id, sender_suffix = suffix.split(":sender:", 1)
            return f"{prefix}:sender:{sender_suffix}"
        return prefix

    def find_session(self, base_key: str) -> SessionRecord | None:
        pointer = self.connection.execute(
            "SELECT active_session_id FROM session_pointers WHERE base_key = ?",
            (base_key,),
        ).fetchone()
        if pointer is None:
            return None
        return self.get_session(pointer["active_session_id"])

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

    def remember_message(self, message_id: str) -> bool:
        now = int(time.time())
        cutoff = now - DEDUP_TTL_SECONDS
        self.connection.execute("DELETE FROM dedup WHERE seen_at < ?", (cutoff,))
        row = self.connection.execute("SELECT seen_at FROM dedup WHERE message_id = ?", (message_id,)).fetchone()
        duplicate = row is not None and int(row["seen_at"] or 0) >= cutoff
        self.connection.execute(
            "INSERT INTO dedup(message_id, seen_at) VALUES(?, ?) ON CONFLICT(message_id) DO UPDATE SET seen_at = excluded.seen_at",
            (message_id, now),
        )
        self.connection.commit()
        return duplicate

    def load_session(self, base_key: str, template: SessionRecord | None = None) -> SessionRecord:
        requested_key = base_key.strip()
        existing = self.find_session(requested_key)
        if existing is not None:
            return existing
        owner_key = self.owner_session_key(requested_key)
        if owner_key != requested_key:
            owner_session = self.find_session(owner_key)
            if owner_session is not None:
                self.bind_scope(requested_key, owner_session.session_id)
                return owner_session
        release_channel = template.release_channel if template and template.release_channel else "main"
        session = SessionRecord(
            session_id=self._new_session_id(),
            base_key=owner_key,
            backend=template.backend if template else self._default_backend(),
            cwd=template.cwd if template else self._default_cwd(release_channel),
            label=template.label if template else "",
            model_override=template.model_override if template else self._default_model(),
            safety_mode=template.safety_mode if template else self._default_mode(),
            native_session_id="",
            release_channel=release_channel,
            last_usage={},
        )
        saved = self.save_session(session)
        if requested_key != owner_key:
            self.bind_scope(requested_key, saved.session_id)
        return saved

    def get_session(self, session_id: str) -> SessionRecord:
        row = self.connection.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown session: {session_id}")
        payload = dict(row)
        try:
            payload["last_usage"] = json.loads(payload.pop("last_usage_json", "{}") or "{}")
        except json.JSONDecodeError:
            payload["last_usage"] = {}
        record = SessionRecord(**payload)
        if not record.release_channel:
            record.release_channel = infer_release_channel(self.config, record)
        return record

    def save_session(self, session: SessionRecord) -> SessionRecord:
        now = utc_now()
        payload = asdict(session)
        payload["base_key"] = self.owner_session_key(str(payload.get("base_key") or ""))
        payload["updated_at"] = now
        if not payload["created_at"]:
            payload["created_at"] = now
        if not payload["release_channel"]:
            payload["release_channel"] = infer_release_channel(self.config, session)
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
        return self.get_session(session.session_id)

    def append_message(self, session_id: str, role: str, content: str) -> None:
        self.connection.execute(
            "INSERT INTO messages(session_id, role, content, created_at) VALUES(?, ?, ?, ?)",
            (session_id, role, content, utc_now()),
        )
        self._truncate_messages(session_id)
        self.connection.commit()

    def list_messages(self, session_id: str) -> list[dict[str, str]]:
        rows = self.connection.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def create_next_session(self, base_key: str, current: SessionRecord | None, label: str = "", **overrides: str) -> SessionRecord:
        requested_key = base_key.strip()
        owner_key = self.owner_session_key(requested_key)
        release_channel = overrides.get("release_channel") or (current.release_channel if current else "main")
        session = SessionRecord(
            session_id=self._new_session_id(),
            base_key=owner_key,
            backend=overrides.get("backend") or (current.backend if current else self._default_backend()),
            cwd=overrides.get("cwd") or (current.cwd if current else self._default_cwd(release_channel)),
            label=label.strip() or "",
            model_override=overrides.get("model_override") if overrides.get("model_override") is not None else (current.model_override if current else self._default_model()),
            safety_mode=overrides.get("safety_mode") or (current.safety_mode if current else self._default_mode()),
            release_channel=release_channel,
            last_usage={},
        )
        saved = self.save_session(session)
        if requested_key != owner_key:
            self.bind_scope(requested_key, saved.session_id)
        return saved

    def _session_scope_patterns(self, base_key: str) -> list[str]:
        key = self.owner_session_key(base_key)
        if not key:
            return []
        if ":sender:" in key:
            prefix, suffix = key.split(":sender:", 1)
            return [key, f"{prefix}:thread:%:sender:{suffix}"]
        return [key, f"{key}:thread:%"]

    def list_sessions(self, base_key: str, limit: int = 20) -> list[SessionSummary]:
        owner_key = self.owner_session_key(base_key)
        pointer = self.connection.execute(
            "SELECT active_session_id FROM session_pointers WHERE base_key = ?",
            (owner_key,),
        ).fetchone()
        active_id = pointer["active_session_id"] if pointer else ""
        if not owner_key:
            return []
        rows = self.connection.execute(
            "SELECT * FROM sessions WHERE base_key = ? ORDER BY updated_at DESC LIMIT ?",
            (owner_key, max(limit * 10, 50)),
        ).fetchall()
        summaries: list[SessionSummary] = []
        for row in rows:
            session_id = row["session_id"]
            message_count = self.count_messages(session_id)
            summaries.append(
                SessionSummary(
                    session_id=session_id,
                    base_key=row["base_key"],
                    backend=row["backend"],
                    label=row["label"] or "",
                    cwd=row["cwd"],
                    native_session_id=row["native_session_id"] or "",
                    updated_at=row["updated_at"],
                    active=session_id == active_id,
                    release_channel=row["release_channel"] or "main",
                    first_user_message=self._first_message(session_id, "user"),
                    last_assistant_message=self._last_message(session_id, "assistant"),
                    message_count=message_count,
                )
            )
        summaries.sort(key=lambda entry: (entry.active, entry.updated_at), reverse=True)
        return summaries[:limit]

    def resume_session(self, base_key: str, target: str) -> SessionRecord | None:
        requested_key = base_key.strip()
        owner_key = self.owner_session_key(requested_key)
        target = target.strip()
        pointer = self.connection.execute(
            "SELECT active_session_id FROM session_pointers WHERE base_key = ?",
            (owner_key,),
        ).fetchone()
        active_id = pointer["active_session_id"] if pointer else ""
        sessions = self.list_sessions(owner_key, limit=50)
        chosen: SessionSummary | None = None
        if not target or target in {"latest", "prev", "previous"}:
            chosen = next((entry for entry in sessions if entry.session_id != active_id), None)
        else:
            chosen = next((entry for entry in sessions if entry.session_id == target), None)
        if chosen is None:
            return None
        self.connection.execute(
            "UPDATE session_pointers SET active_session_id = ?, updated_at = ? WHERE base_key = ?",
            (chosen.session_id, utc_now(), owner_key),
        )
        self.connection.commit()
        if requested_key and requested_key != owner_key:
            self.bind_scope(requested_key, chosen.session_id)
        return self.get_session(chosen.session_id)

    def clear_sessions(self, base_key: str) -> None:
        owner_key = self.owner_session_key(base_key)
        rows = self.connection.execute("SELECT session_id FROM sessions WHERE base_key = ?", (owner_key,)).fetchall()
        ids = [row["session_id"] for row in rows]
        self.connection.execute("DELETE FROM sessions WHERE base_key = ?", (owner_key,))
        patterns = self._session_scope_patterns(owner_key)
        if patterns:
            where_clause = " OR ".join("base_key LIKE ?" if "%" in pattern else "base_key = ?" for pattern in patterns)
            self.connection.execute(f"DELETE FROM session_pointers WHERE {where_clause}", patterns)
        if ids:
            self.connection.executemany("DELETE FROM messages WHERE session_id = ?", [(session_id,) for session_id in ids])
        self.connection.commit()



def hash_key(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()
