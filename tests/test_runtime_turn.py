from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from openrelay.core import IncomingMessage, SessionRecord
from openrelay.runtime.turn import BackendTurnSession, TurnRuntimeContext


class _DummyStreamingSession:
    def __init__(self) -> None:
        self.closed_with: dict[str, object] | None = None

    def has_started(self) -> bool:
        return True

    async def close(self, final_card: dict[str, object] | None = None) -> None:
        self.closed_with = final_card


def _build_runtime_context(tmp_path: Path) -> TurnRuntimeContext:
    config = SimpleNamespace(feishu=SimpleNamespace(stream_mode="card"))
    messenger = object()
    return TurnRuntimeContext(
        config=config,
        store=SimpleNamespace(),
        messenger=messenger,
        typing_manager=SimpleNamespace(),
        session_ux=SimpleNamespace(
            format_cwd=lambda cwd, session=None: str(cwd),
            label_session_if_needed=lambda session, summary: session,
            shorten=lambda text, max_length=96: str(text)[:max_length],
        ),
        streaming_session_factory=lambda current_messenger: _DummyStreamingSession(),
        execution_coordinator=SimpleNamespace(start_run=lambda *args, **kwargs: None, finish_run=lambda *args, **kwargs: None),
        build_card_action_context=lambda message, session_key: {},
        streaming_route_for_message=lambda message: SimpleNamespace(reply_to_message_id="", root_id="", force_new_message=False),
        root_id_for_message=lambda message: "",
        is_card_action_message=lambda message: False,
        build_session_key=lambda message: "session:test",
        remember_outbound_aliases=lambda message, session_key, alias_ids: None,
        reply_final=lambda message, text, streaming, live_state: asyncio.sleep(0),
        live_turn_presenter=None,
        binding_store=None,
        runtime_service=None,
    )


def _build_message() -> IncomingMessage:
    return IncomingMessage(
        event_id="evt_stop",
        message_id="om_stop",
        chat_id="oc_test",
        chat_type="p2p",
        sender_open_id="ou_user",
        text="hello",
        actionable=True,
    )


def _build_session(tmp_path: Path) -> SessionRecord:
    return SessionRecord(
        session_id="session_1",
        base_key="base_1",
        backend="codex",
        cwd=str(tmp_path),
    )


@pytest.mark.asyncio
async def test_backend_turn_cancel_closes_streaming_card_and_blocks_follow_up_updates(tmp_path: Path) -> None:
    turn = BackendTurnSession(
        _build_runtime_context(tmp_path),
        _build_message(),
        "session:session_1",
        _build_session(tmp_path),
    )
    streaming = _DummyStreamingSession()
    turn.streaming = streaming
    turn.live_state["partial_text"] = "still streaming"
    turn.pending_streaming_states.append({"partial_text": "stale"})
    turn.spinner_task = asyncio.create_task(asyncio.sleep(60))

    await turn.cancel("interrupted by /stop")
    turn._request_streaming_update()
    await asyncio.sleep(0)

    assert turn.cancel_event.is_set() is True
    assert turn.spinner_task is None
    assert list(turn.pending_streaming_states) == []
    assert turn.streaming_update_event.is_set() is False
    assert streaming.closed_with is not None
    assert "已停止当前回复。" in str(streaming.closed_with)
