from __future__ import annotations

import json
import sqlite3
from typing import Iterable

from .models import MessageEventRecord


class MessageEventStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def init_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS message_event_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              trace_id TEXT NOT NULL,
              occurred_at TEXT NOT NULL,
              level TEXT NOT NULL,
              stage TEXT NOT NULL,
              event_type TEXT NOT NULL,
              backend TEXT NOT NULL DEFAULT '',
              relay_session_id TEXT NOT NULL DEFAULT '',
              session_key TEXT NOT NULL DEFAULT '',
              execution_key TEXT NOT NULL DEFAULT '',
              turn_id TEXT NOT NULL DEFAULT '',
              native_session_id TEXT NOT NULL DEFAULT '',
              incoming_event_id TEXT NOT NULL DEFAULT '',
              incoming_message_id TEXT NOT NULL DEFAULT '',
              reply_message_id TEXT NOT NULL DEFAULT '',
              chat_id TEXT NOT NULL DEFAULT '',
              root_id TEXT NOT NULL DEFAULT '',
              thread_id TEXT NOT NULL DEFAULT '',
              parent_id TEXT NOT NULL DEFAULT '',
              source_kind TEXT NOT NULL DEFAULT '',
              summary TEXT NOT NULL DEFAULT '',
              payload_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_message_event_log_trace
              ON message_event_log(trace_id, id ASC);
            CREATE INDEX IF NOT EXISTS idx_message_event_log_session
              ON message_event_log(relay_session_id, id ASC);
            CREATE INDEX IF NOT EXISTS idx_message_event_log_turn
              ON message_event_log(turn_id, id ASC);
            CREATE INDEX IF NOT EXISTS idx_message_event_log_incoming_message
              ON message_event_log(incoming_message_id, id ASC);
            CREATE INDEX IF NOT EXISTS idx_message_event_log_event_type_time
              ON message_event_log(event_type, occurred_at DESC);
            """
        )
        self.connection.commit()

    def append(self, record: MessageEventRecord) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO message_event_log(
              trace_id, occurred_at, level, stage, event_type, backend,
              relay_session_id, session_key, execution_key, turn_id, native_session_id,
              incoming_event_id, incoming_message_id, reply_message_id, chat_id,
              root_id, thread_id, parent_id, source_kind, summary, payload_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.trace_id,
                record.occurred_at,
                record.level,
                record.stage,
                record.event_type,
                record.backend,
                record.relay_session_id,
                record.session_key,
                record.execution_key,
                record.turn_id,
                record.native_session_id,
                record.incoming_event_id,
                record.incoming_message_id,
                record.reply_message_id,
                record.chat_id,
                record.root_id,
                record.thread_id,
                record.parent_id,
                record.source_kind,
                record.summary,
                json.dumps(record.payload, ensure_ascii=False, sort_keys=True, default=str),
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid or 0)

    def append_many(self, records: Iterable[MessageEventRecord]) -> None:
        self.connection.executemany(
            """
            INSERT INTO message_event_log(
              trace_id, occurred_at, level, stage, event_type, backend,
              relay_session_id, session_key, execution_key, turn_id, native_session_id,
              incoming_event_id, incoming_message_id, reply_message_id, chat_id,
              root_id, thread_id, parent_id, source_kind, summary, payload_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.trace_id,
                    record.occurred_at,
                    record.level,
                    record.stage,
                    record.event_type,
                    record.backend,
                    record.relay_session_id,
                    record.session_key,
                    record.execution_key,
                    record.turn_id,
                    record.native_session_id,
                    record.incoming_event_id,
                    record.incoming_message_id,
                    record.reply_message_id,
                    record.chat_id,
                    record.root_id,
                    record.thread_id,
                    record.parent_id,
                    record.source_kind,
                    record.summary,
                    json.dumps(record.payload, ensure_ascii=False, sort_keys=True, default=str),
                )
                for record in records
            ],
        )
        self.connection.commit()

    def list_by_trace(self, trace_id: str, limit: int = 500) -> list[MessageEventRecord]:
        return self._list("trace_id = ?", (trace_id, limit))

    def list_by_session(self, relay_session_id: str, limit: int = 500) -> list[MessageEventRecord]:
        return self._list("relay_session_id = ?", (relay_session_id, limit))

    def list_by_turn(self, turn_id: str, limit: int = 500) -> list[MessageEventRecord]:
        return self._list("turn_id = ?", (turn_id, limit))

    def list_by_message(self, incoming_message_id: str, limit: int = 500) -> list[MessageEventRecord]:
        return self._list("incoming_message_id = ?", (incoming_message_id, limit))

    def prune_before(self, cutoff: str) -> int:
        cursor = self.connection.execute("DELETE FROM message_event_log WHERE occurred_at < ?", (cutoff,))
        self.connection.commit()
        return int(cursor.rowcount or 0)

    def _list(self, where_clause: str, params: tuple[object, ...]) -> list[MessageEventRecord]:
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM message_event_log
            WHERE {where_clause}
            ORDER BY id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def _from_row(self, row: sqlite3.Row) -> MessageEventRecord:
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except json.JSONDecodeError:
            payload = {"invalid_payload_json": str(row["payload_json"] or "")}
        if not isinstance(payload, dict):
            payload = {"value": payload}
        return MessageEventRecord(
            trace_id=str(row["trace_id"] or ""),
            occurred_at=str(row["occurred_at"] or ""),
            level=str(row["level"] or ""),
            stage=str(row["stage"] or ""),
            event_type=str(row["event_type"] or ""),
            backend=str(row["backend"] or ""),
            relay_session_id=str(row["relay_session_id"] or ""),
            session_key=str(row["session_key"] or ""),
            execution_key=str(row["execution_key"] or ""),
            turn_id=str(row["turn_id"] or ""),
            native_session_id=str(row["native_session_id"] or ""),
            incoming_event_id=str(row["incoming_event_id"] or ""),
            incoming_message_id=str(row["incoming_message_id"] or ""),
            reply_message_id=str(row["reply_message_id"] or ""),
            chat_id=str(row["chat_id"] or ""),
            root_id=str(row["root_id"] or ""),
            thread_id=str(row["thread_id"] or ""),
            parent_id=str(row["parent_id"] or ""),
            source_kind=str(row["source_kind"] or ""),
            summary=str(row["summary"] or ""),
            payload=payload,
            row_id=int(row["id"] or 0),
        )
