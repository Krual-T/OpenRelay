from __future__ import annotations

import sqlite3

from openrelay.core import SessionRecord, utc_now
from openrelay.storage import StateStore

from .models import RelaySessionBinding


class SessionBindingStore:
    def __init__(self, store: StateStore) -> None:
        self.store = store
        self._init_schema()

    def _init_schema(self) -> None:
        self.store.connection.execute(
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
        self.store.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_relay_bindings_scope_updated ON relay_session_bindings(feishu_chat_id, feishu_thread_id, updated_at DESC)"
        )
        self.store.connection.commit()

    def save(self, binding: RelaySessionBinding) -> None:
        now = utc_now()
        created_at = binding.created_at or now
        self.store.connection.execute(
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
        self.store.connection.commit()
        self._sync_session_record(binding)

    def get(self, relay_session_id: str) -> RelaySessionBinding | None:
        row = self.store.connection.execute(
            "SELECT * FROM relay_session_bindings WHERE relay_session_id = ?",
            (relay_session_id,),
        ).fetchone()
        return None if row is None else self._binding_from_row(row)

    def find_by_feishu_scope(self, chat_id: str, thread_id: str) -> RelaySessionBinding | None:
        row = self.store.connection.execute(
            """
            SELECT * FROM relay_session_bindings
            WHERE feishu_chat_id = ? AND feishu_thread_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (chat_id, thread_id),
        ).fetchone()
        if row is None and not thread_id:
            row = self.store.connection.execute(
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
        params = (*params, max(limit, 1))
        rows = self.store.connection.execute(query, params).fetchall()
        return [self._binding_from_row(row) for row in rows]

    def update_native_session_id(self, relay_session_id: str, native_session_id: str) -> None:
        now = utc_now()
        self.store.connection.execute(
            """
            UPDATE relay_session_bindings
            SET native_session_id = ?, updated_at = ?
            WHERE relay_session_id = ?
            """,
            (native_session_id, now, relay_session_id),
        )
        self.store.connection.commit()
        binding = self.get(relay_session_id)
        if binding is not None:
            self._sync_session_record(binding)

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

    def _sync_session_record(self, binding: RelaySessionBinding) -> None:
        try:
            session = self.store.get_session(binding.relay_session_id)
        except KeyError:
            return
        synced = SessionRecord(
            session_id=session.session_id,
            base_key=session.base_key,
            backend=binding.backend,
            cwd=binding.cwd,
            label=session.label,
            model_override=binding.model,
            safety_mode=binding.safety_mode,
            native_session_id=binding.native_session_id,
            release_channel=session.release_channel,
            last_usage=session.last_usage,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )
        self.store.save_session(synced)
