from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from openrelay.agent_runtime import RuntimeEvent, TurnInput
from openrelay.agent_runtime.backend import RuntimeEventSink
from openrelay.backends.codex_adapter.app_server import InterruptedError
from openrelay.backends.codex_adapter.mapper import CodexProtocolMapper, CodexTurnState
from openrelay.backends.codex_adapter.transport import CodexRpcTransport
from openrelay.backends.codex_adapter.turn_stream import CodexTurnStream
from openrelay.core.config import load_config


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JsonlTraceRecorder:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.output_path.open("w", encoding="utf-8")

    def write(self, record_type: str, payload: dict[str, Any]) -> None:
        record = {
            "recorded_at": utc_now(),
            "record_type": str(record_type or "").strip(),
            **payload,
        }
        self._handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str))
        self._handle.write("\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


@dataclass(slots=True)
class TraceWriters:
    raw: JsonlTraceRecorder
    mapped: JsonlTraceRecorder

    def write_raw(self, record_type: str, payload: dict[str, Any]) -> None:
        self.raw.write(record_type, payload)

    def write_mapped(self, record_type: str, payload: dict[str, Any]) -> None:
        self.mapped.write(record_type, payload)

    def close(self) -> None:
        self.raw.close()
        self.mapped.close()


def serialize_runtime_event(event: RuntimeEvent) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event_class": event.__class__.__name__,
        "event_type": event.event_type,
        "backend": event.backend,
        "session_id": event.session_id,
        "turn_id": event.turn_id,
        "created_at": event.created_at,
        "provider_payload": dict(event.provider_payload),
    }
    if is_dataclass(event):
        base_fields = {"backend", "session_id", "turn_id", "event_type", "created_at", "provider_payload"}
        for item in fields(event):
            if item.name in base_fields:
                continue
            payload[item.name] = getattr(event, item.name)
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one Codex app-server query and capture a full jsonl trace.")
    parser.add_argument("--query", required=True, help="Prompt to send to Codex app-server.")
    parser.add_argument("--output", default="", help="Output jsonl path. Defaults under .harness/traces/.")
    parser.add_argument("--cwd", default="", help="Working directory for the app-server thread. Defaults to current repo cwd.")
    parser.add_argument("--model", default="", help="Optional model override.")
    parser.add_argument("--safety-mode", default="", help="Optional safety mode override.")
    parser.add_argument("--thread-id", default="", help="Optional existing native thread id to resume.")
    parser.add_argument("--session-id", default="", help="Optional synthetic relay session id for the trace.")
    return parser.parse_args(argv)


def default_output_paths(root: Path) -> tuple[Path, Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trace_root = root / ".harness" / "traces"
    return (
        trace_root / f"codex-app-server-raw-{stamp}.jsonl",
        trace_root / f"codex-app-server-mapped-{stamp}.jsonl",
    )


def resolve_output_paths(root: Path, output: str) -> tuple[Path, Path]:
    if not output:
        return default_output_paths(root)
    requested = Path(output).expanduser().resolve()
    if requested.suffix == ".jsonl":
        stem_path = requested.with_suffix("")
    else:
        stem_path = requested
    return (
        stem_path.parent / f"{stem_path.name}-raw.jsonl",
        stem_path.parent / f"{stem_path.name}-mapped.jsonl",
    )


def serialize_thread_details(details: Any) -> dict[str, Any]:
    return {
        "thread_id": str(getattr(details, "thread_id", "") or ""),
        "preview": str(getattr(details, "preview", "") or ""),
        "cwd": str(getattr(details, "cwd", "") or ""),
        "updated_at": str(getattr(details, "updated_at", "") or ""),
        "status": str(getattr(details, "status", "") or ""),
        "name": str(getattr(details, "name", "") or ""),
        "messages": [
            {
                "role": str(getattr(message, "role", "") or ""),
                "text": str(getattr(message, "text", "") or ""),
            }
            for message in tuple(getattr(details, "messages", ()) or ())
        ],
    }


def serialize_turn_state(stream: CodexTurnStream) -> dict[str, Any]:
    state = stream.state
    return {
        "native_session_id": stream.native_session_id,
        "turn_id": stream.turn_id,
        "done": stream.done,
        "final_text": state.final_text,
        "agent_text_by_id": dict(state.agent_text_by_id),
        "command_output_by_id": dict(state.command_output_by_id),
        "file_change_output_by_id": dict(state.file_change_output_by_id),
        "reasoning_order": list(state.reasoning_order),
        "system_snapshot": dict(state.system_snapshot),
    }


class _RecordingSink(RuntimeEventSink):
    def __init__(self, recorder: JsonlTraceRecorder) -> None:
        self.recorder = recorder
        self.events: list[RuntimeEvent] = []

    async def publish(self, event: RuntimeEvent) -> None:
        self.events.append(event)
        self.recorder.write("runtime_event", serialize_runtime_event(event))


async def run_trace(args: argparse.Namespace) -> tuple[Path, Path]:
    config = load_config()
    cwd = str(Path(args.cwd or config.cwd).expanduser().resolve())
    raw_output_path, mapped_output_path = resolve_output_paths(config.cwd, args.output)
    session_id = str(args.session_id or f"trace-{uuid4().hex}")
    safety_mode = str(args.safety_mode or config.backend.default_safety_mode or "workspace-write")
    model = str(args.model or config.backend.default_model or "")
    writers = TraceWriters(
        raw=JsonlTraceRecorder(raw_output_path),
        mapped=JsonlTraceRecorder(mapped_output_path),
    )
    sink = _RecordingSink(writers.mapped)
    transport = CodexRpcTransport(
        codex_path=config.backend.codex_cli_path,
        workspace_root=Path(cwd),
        sqlite_home=config.backend.codex_sqlite_home,
        model=model,
        safety_mode=safety_mode,
        request_timeout_seconds=config.backend.codex_request_timeout_seconds,
    )
    mapper = CodexProtocolMapper(session_id=session_id, native_session_id=str(args.thread_id or ""))
    stream = CodexTurnStream(
        session_id=session_id,
        native_session_id=str(args.thread_id or ""),
        sink=sink,
        mapper=mapper,
        transport=transport,
    )

    async def notify_handler(method: str, params: dict[str, Any]) -> None:
        writers.write_raw(
            "notification",
            {
                "method": method,
                "params": params,
            },
        )
        await stream.handle_notification(method, params)

    async def server_handler(request_id: int | str, method: str, params: dict[str, Any]) -> bool:
        writers.write_raw(
            "server_request",
            {
                "request_id": request_id,
                "method": method,
                "params": params,
            },
        )
        handled = await stream.handle_server_request(request_id, method, params)
        writers.write_mapped("server_request_result", {"request_id": request_id, "method": method, "handled": handled})
        return handled

    writers.write_mapped(
        "trace_started",
        {
            "session_id": session_id,
            "cwd": cwd,
            "model": model,
            "safety_mode": safety_mode,
            "query": args.query,
            "thread_id": str(args.thread_id or ""),
        },
    )
    transport.subscribe_notifications(notify_handler)
    transport.subscribe_server_requests(server_handler)
    try:
        thread_id = str(args.thread_id or "")
        if thread_id:
            resume_params = {
                **mapper.build_thread_params(
                    cwd=cwd,
                    model=model,
                    safety_mode=safety_mode,
                    default_model=config.backend.default_model,
                ),
                "threadId": thread_id,
            }
            writers.write_mapped("request", {"method": "thread/resume", "params": resume_params})
            resume_result = await transport.request("thread/resume", resume_params)
            writers.write_raw("response", {"method": "thread/resume", "result": resume_result})
        else:
            thread_params = mapper.build_thread_params(
                cwd=cwd,
                model=model,
                safety_mode=safety_mode,
                default_model=config.backend.default_model,
            )
            writers.write_mapped("request", {"method": "thread/start", "params": thread_params})
            start_result = await transport.request("thread/start", thread_params)
            writers.write_raw("response", {"method": "thread/start", "result": start_result})
            thread = start_result.get("thread") if isinstance(start_result, dict) and isinstance(start_result.get("thread"), dict) else {}
            thread_id = str(thread.get("id") or "")
        if not thread_id:
            raise RuntimeError("Codex app-server returned no thread id")

        stream.native_session_id = thread_id
        mapper.native_session_id = thread_id
        turn_params = mapper.build_turn_start_params(
            thread_id=thread_id,
            turn_input=TurnInput(
                text=args.query,
                cwd=cwd,
                model=model or None,
                safety_mode=safety_mode,
            ),
        )
        writers.write_mapped("request", {"method": "turn/start", "params": turn_params})
        turn_result = await transport.request("turn/start", turn_params)
        writers.write_raw("response", {"method": "turn/start", "result": turn_result})
        turn = turn_result.get("turn") if isinstance(turn_result, dict) and isinstance(turn_result.get("turn"), dict) else {}
        turn_id = str(turn.get("id") or "")
        await stream.bind_started_turn(turn_id)
        writers.write_mapped(
            "turn_bound",
            {
                "thread_id": thread_id,
                "turn_id": stream.turn_id,
            },
        )
        try:
            await stream.future
            writers.write_mapped("turn_result", {"status": "completed"})
        except InterruptedError as exc:
            writers.write_mapped("turn_result", {"status": "interrupted", "message": str(exc)})
            raise
        except Exception as exc:
            writers.write_mapped("turn_result", {"status": "failed", "message": str(exc)})
            raise
        details = await transport.read_thread(thread_id, include_turns=True)
        writers.write_mapped("thread_read", serialize_thread_details(details))
        writers.write_mapped("turn_state", serialize_turn_state(stream))
        return raw_output_path, mapped_output_path
    finally:
        transport.unsubscribe_notifications(notify_handler)
        transport.unsubscribe_server_requests(server_handler)
        await transport.stop()
        writers.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    raw_output_path, mapped_output_path = asyncio.run(run_trace(args))
    print(json.dumps({"raw_output": str(raw_output_path), "mapped_output": str(mapped_output_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
