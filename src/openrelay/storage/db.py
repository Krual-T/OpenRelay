from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from openrelay.core import AppConfig

DB_FILENAME = "openrelay.sqlite3"
LEGACY_DB_FILENAME = "agentmux.sqlite3"


@dataclass(slots=True)
class SqliteStateContext:
    config: AppConfig
    db_path: Path
    connection: sqlite3.Connection

    @classmethod
    def open(cls, config: AppConfig) -> "SqliteStateContext":
        config.data_dir.mkdir(parents=True, exist_ok=True)
        db_path = resolve_db_path(config)
        connection = sqlite3.connect(db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        context = cls(config=config, db_path=db_path, connection=connection)
        context.init_schema()
        return context

    def close(self) -> None:
        self.connection.close()

    def init_schema(self) -> None:
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


def resolve_db_path(config: AppConfig) -> Path:
    db_path = config.data_dir / DB_FILENAME
    legacy_db_path = config.data_dir / LEGACY_DB_FILENAME
    if db_path.exists() or not legacy_db_path.exists():
        return db_path
    legacy_db_path.replace(db_path)
    for suffix in ("-shm", "-wal"):
        legacy_sidecar_path = Path(f"{legacy_db_path}{suffix}")
        if legacy_sidecar_path.exists():
            legacy_sidecar_path.replace(Path(f"{db_path}{suffix}"))
    return db_path
