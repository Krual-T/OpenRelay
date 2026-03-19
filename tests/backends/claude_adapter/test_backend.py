from __future__ import annotations

from pathlib import Path

import pytest

from openrelay.agent_runtime import AssistantCompletedEvent, SessionStartedEvent, TurnCompletedEvent, TurnInput
from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.backends.claude_adapter.backend import ClaudeRuntimeBackend
from openrelay.backends.registry import build_builtin_backend_descriptors
from openrelay.session import RelayScope, RelaySessionBinding
from openrelay.session.store import SessionBindingStore
from openrelay.storage import StateStore
from tests.support.app import make_app_config

class FakeClaudeTransport:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, object]] = []
        self.workspace_root = Path("/workspace")

    async def run(
        self,
        *,
        prompt: str,
        cwd: str,
        model: str | None,
        safety_mode: str,
        session_id: str = "",
        cancel_event=None,
    ):
        _ = cancel_event
        self.calls.append(
            {
                "prompt": prompt,
                "cwd": cwd,
                "model": model,
                "safety_mode": safety_mode,
                "session_id": session_id,
            }
        )
        return type("ClaudeCliResult", (), {"stdout": self.text, "stderr": ""})()


@pytest.mark.asyncio
async def test_claude_runtime_backend_runs_turn_and_publishes_runtime_events(tmp_path: Path) -> None:
    backend = ClaudeRuntimeBackend("claude", workspace_root=tmp_path)
    transport = FakeClaudeTransport('{"result":"hello from claude","session_id":"claude_native_1"}')
    backend._clients[str(tmp_path.resolve())] = backend._get_client("")
    backend._clients[str(tmp_path.resolve())].transport = transport

    events = []

    class Sink:
        async def publish(self, event) -> None:
            events.append(event)

    handle = await backend.start_turn(
        RelaySessionBinding(
            relay_session_id="relay_1",
            backend="claude",
            native_session_id="",
            cwd=str(tmp_path),
            model="",
            safety_mode="workspace-write",
            feishu_chat_id="oc_1",
            feishu_thread_id="",
        ).locator,
        TurnInput(text="hello", cwd=str(tmp_path), metadata={"relay_session_id": "relay_1"}),
        Sink(),
    )
    await handle.wait()

    assert any(isinstance(event, SessionStartedEvent) for event in events)
    assert any(isinstance(event, AssistantCompletedEvent) and event.text == "hello from claude" for event in events)
    assert any(isinstance(event, TurnCompletedEvent) and event.final_text == "hello from claude" for event in events)
    assert transport.calls[0]["prompt"] == "hello"


@pytest.mark.asyncio
async def test_agent_runtime_service_can_mount_claude_backend_without_session_listing_support(tmp_path: Path) -> None:
    config = make_app_config(tmp_path, verify_token=None, bot_open_id=None)
    store = StateStore(config)
    bindings = SessionBindingStore(store)
    backend = ClaudeRuntimeBackend("claude", workspace_root=tmp_path)
    service = AgentRuntimeService({"claude": backend}, bindings)

    binding = await service.start_new_session(
        "claude",
        request=type("Req", (), {"cwd": str(tmp_path), "model": "", "safety_mode": "workspace-write", "metadata": {}})(),
        scope=RelayScope(relay_session_id="relay_1", feishu_chat_id="oc_1", feishu_thread_id=""),
    )

    assert binding.backend == "claude"
    assert build_builtin_backend_descriptors()["claude"].transport == "cli-json"
    store.close()
