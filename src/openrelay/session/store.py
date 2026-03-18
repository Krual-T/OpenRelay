from __future__ import annotations

import sqlite3

from openrelay.core import utc_now
from openrelay.storage.db import SqliteStateContext

from .models import RelaySessionBinding


class SessionBindingStore:
    def __init__(self, context_or_store: object) -> None:
        self.context = self._resolve_context(context_or_store)
        self.connection = self.context.connection
        self._init_schema()

    def _resolve_context(self, context_or_store: object) -> SqliteStateContext:
        if isinstance(context_or_store, SqliteStateContext):
            return context_or_store
        context = getattr(context_or_store, "context", None)
        if isinstance(context, SqliteStateContext):
            return context
        raise TypeError("SessionBindingStore requires SqliteStateContext or StateStore-like context holder")

    def _init_schema(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS relay_session_bindings (
              relay_session_id TEXT PRIMARY KEY,
              backend TEXT NOT NULL,
              native_session_id TEXT NOT NULL DEFAULT '',
              cwd TEXT NOT NULL,
              model TEXT NOT NULL DEFAULT '',
              safety_mode TEXT NOT NULL,
              feishu_chat_id TEXT NOT NULL,
              feishu_thread_id TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_relay_bindings_scope_updated ON relay_session_bindings(feishu_chat_id, feishu_thread_id, updated_at DESC)"
        )
        self.connection.commit()

    def save(self, binding: RelaySessionBinding) -> RelaySessionBinding:
        now = utc_now()
        created_at = binding.created_at or now
        self.connection.execute(
            """
            INSERT INTO relay_session_bindings(
              relay_session_id, backend, native_session_id, cwd, model, safety_mode,
              feishu_chat_id, feishu_thread_id, created_at, updated_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(relay_session_id) DO UPDATE SET
              backend = excluded.backend,
              native_session_id = excluded.native_session_id,
              cwd = excluded.cwd,
              model = excluded.model,
              safety_mode = excluded.safety_mode,
              feishu_chat_id = excluded.feishu_chat_id,
              feishu_thread_id = excluded.feishu_thread_id,
              updated_at = excluded.updated_at
            """,
            (
                binding.relay_session_id,
                binding.backend,
                binding.native_session_id,
                binding.cwd,
                binding.model,
                binding.safety_mode,
                binding.feishu_chat_id,
                binding.feishu_thread_id,
                created_at,
                now,
            ),
        )
        self.connection.commit()
        return self.get(binding.relay_session_id) or binding

    def get(self, relay_session_id: str) -> RelaySessionBinding | None:
        row = self.connection.execute(
            "SELECT * FROM relay_session_bindings WHERE relay_session_id = ?",
            (relay_session_id,),
        ).fetchone()
        return None if row is None else self._binding_from_row(row)

    def find_by_feishu_scope(self, chat_id: str, thread_id: str) -> RelaySessionBinding | None:
        row = self.connection.execute(
            """
            SELECT * FROM relay_session_bindings
            WHERE feishu_chat_id = ? AND feishu_thread_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (chat_id, thread_id),
        ).fetchone()
        if row is None and not thread_id:
            row = self.connection.execute(
                """
                SELECT * FROM relay_session_bindings
                WHERE feishu_chat_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (chat_id,),
            ).fetchone()
        return None if row is None else self._binding_from_row(row)

    def list_recent(self, backend: str | None = None, limit: int = 20) -> list[RelaySessionBinding]:
        query = "SELECT * FROM relay_session_bindings"
        params: tuple[object, ...] = ()
        if backend is not None:
            query += " WHERE backend = ?"
            params = (backend,)
        query += " ORDER BY updated_at DESC LIMIT ?"
        rows = self.connection.execute(query, (*params, max(limit, 1))).fetchall()
        return [self._binding_from_row(row) for row in rows]

    def update_native_session_id(self, relay_session_id: str, native_session_id: str) -> None:
        self.connection.execute(
            """
            UPDATE relay_session_bindings
            SET native_session_id = ?, updated_at = ?
            WHERE relay_session_id = ?
            """,
            (native_session_id, utc_now(), relay_session_id),
        )
        self.connection.commit()

    def clear(self, relay_session_id: str) -> None:
        self.connection.execute(
            "DELETE FROM relay_session_bindings WHERE relay_session_id = ?",
            (relay_session_id,),
        )
        self.connection.commit()

    def clear_many(self, relay_session_ids: list[str]) -> None:
        if not relay_session_ids:
            return
        self.connection.executemany(
            "DELETE FROM relay_session_bindings WHERE relay_session_id = ?",
            [(relay_session_id,) for relay_session_id in relay_session_ids],
        )
        self.connection.commit()

    def _binding_from_row(self, row: sqlite3.Row) -> RelaySessionBinding:
        return RelaySessionBinding(
            relay_session_id=str(row["relay_session_id"] or ""),
            backend=str(row["backend"] or "codex"),  # type: ignore[arg-type]
            native_session_id=str(row["native_session_id"] or ""),
            cwd=str(row["cwd"] or ""),
            model=str(row["model"] or ""),
            safety_mode=str(row["safety_mode"] or ""),
            feishu_chat_id=str(row["feishu_chat_id"] or ""),
            feishu_thread_id=str(row["feishu_thread_id"] or ""),
            created_at=str(row["created_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )
