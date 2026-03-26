import json
from pathlib import Path

from openrelay.agent_runtime import AssistantDeltaEvent
from openrelay.tools.codex_app_server_trace import (
    JsonlTraceRecorder,
    TraceWriters,
    default_output_paths,
    serialize_runtime_event,
)


def test_serialize_runtime_event_preserves_provider_payload() -> None:
    event = AssistantDeltaEvent(
        backend="codex",
        session_id="relay_1",
        turn_id="turn_1",
        event_type="assistant.delta",
        delta="hello",
        provider_payload={"phase": "commentary", "method": "item/agentMessage/delta"},
    )

    payload = serialize_runtime_event(event)

    assert payload["event_type"] == "assistant.delta"
    assert payload["event_class"] == "AssistantDeltaEvent"
    assert payload["delta"] == "hello"
    assert payload["provider_payload"]["phase"] == "commentary"


def test_jsonl_trace_recorder_writes_jsonl_lines(tmp_path: Path) -> None:
    output_path = tmp_path / "trace.jsonl"
    recorder = JsonlTraceRecorder(output_path)

    recorder.write("notification", {"method": "turn/started", "turn_id": "turn_1"})
    recorder.write("runtime_event", {"event_type": "turn.started"})
    recorder.close()

    lines = output_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["record_type"] == "notification"
    assert first["method"] == "turn/started"
    assert second["record_type"] == "runtime_event"
    assert second["event_type"] == "turn.started"


def test_default_output_paths_return_raw_and_mapped_files(tmp_path: Path) -> None:
    raw_path, mapped_path = default_output_paths(tmp_path)

    assert raw_path.parent == tmp_path / ".harness" / "traces"
    assert mapped_path.parent == tmp_path / ".harness" / "traces"
    assert raw_path.name.startswith("codex-app-server-raw-")
    assert mapped_path.name.startswith("codex-app-server-mapped-")
    assert raw_path.suffix == ".jsonl"
    assert mapped_path.suffix == ".jsonl"


def test_trace_writers_split_raw_and_mapped_records(tmp_path: Path) -> None:
    raw_output = tmp_path / "raw.jsonl"
    mapped_output = tmp_path / "mapped.jsonl"
    writers = TraceWriters(
        raw=JsonlTraceRecorder(raw_output),
        mapped=JsonlTraceRecorder(mapped_output),
    )

    writers.write_raw("notification", {"method": "turn/completed"})
    writers.write_mapped("runtime_event", {"event_type": "turn.completed"})
    writers.close()

    raw_lines = raw_output.read_text(encoding="utf-8").splitlines()
    mapped_lines = mapped_output.read_text(encoding="utf-8").splitlines()

    assert len(raw_lines) == 1
    assert len(mapped_lines) == 1
    assert json.loads(raw_lines[0])["record_type"] == "notification"
    assert json.loads(mapped_lines[0])["record_type"] == "runtime_event"
