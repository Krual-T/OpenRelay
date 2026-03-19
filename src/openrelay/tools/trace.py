from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from openrelay.storage.db import DB_FILENAME

from openrelay.observability import MessageEventStore, TraceQueryService


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read persisted openrelay message traces.")
    parser.add_argument("--db", default="", help="SQLite db path. Defaults to ./data/openrelay.sqlite3")
    parser.add_argument("--trace-id", default="", help="Filter by trace id")
    parser.add_argument("--session-id", default="", help="Filter by relay session id")
    parser.add_argument("--turn-id", default="", help="Filter by turn id")
    parser.add_argument("--message-id", default="", help="Filter by incoming message id")
    parser.add_argument("--limit", type=int, default=200, help="Max events to print")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text")
    return parser.parse_args(argv)


def resolve_db_path(raw_path: str) -> Path:
    if raw_path:
        return Path(raw_path).expanduser().resolve()
    return (Path.cwd() / "data" / DB_FILENAME).resolve()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if sum(bool(value) for value in [args.trace_id, args.session_id, args.turn_id, args.message_id]) != 1:
        print("exactly one of --trace-id / --session-id / --turn-id / --message-id is required", file=sys.stderr)
        return 2
    db_path = resolve_db_path(args.db)
    if not db_path.exists():
        print(f"db not found: {db_path}", file=sys.stderr)
        return 1
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    try:
        query = TraceQueryService(MessageEventStore(connection))
        events = query.list_events(
            trace_id=args.trace_id,
            relay_session_id=args.session_id,
            turn_id=args.turn_id,
            incoming_message_id=args.message_id,
            limit=max(args.limit, 1),
        )
    finally:
        connection.close()
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "id": event.row_id,
                        "occurred_at": event.occurred_at,
                        "stage": event.stage,
                        "event_type": event.event_type,
                        "level": event.level,
                        "trace_id": event.trace_id,
                        "relay_session_id": event.relay_session_id,
                        "turn_id": event.turn_id,
                        "incoming_message_id": event.incoming_message_id,
                        "reply_message_id": event.reply_message_id,
                        "summary": event.summary,
                        "payload": event.payload,
                    }
                    for event in events
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    for event in events:
        line = f"[{event.row_id}] {event.occurred_at} {event.stage}/{event.event_type}"
        if event.summary:
            line = f"{line} - {event.summary}"
        print(line)
        if event.payload:
            print(f"    payload={json.dumps(event.payload, ensure_ascii=False, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
