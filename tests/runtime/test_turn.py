from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from openrelay.core import IncomingMessage, SessionRecord
from openrelay.presentation.live_turn import LiveTurnPresenter
from openrelay.runtime.turn import TurnRuntimeContext
from openrelay.runtime.turn_run_controller import TurnRunController


class _DummyStreamingSession:
    def __init__(self) -> None:
        self.closed_with: dict[str, object] | None = None

    def has_started(self) -> bool:
        return True

    async def close(self, final_card: dict[str, object] | None = None) -> None:
        self.closed_with = final_card


class _RolloverStreamingSession:
    def __init__(self) -> None:
        self.frozen_with: tuple[dict[str, object], str] | None = None

    def has_started(self) -> bool:
        return True

    def is_active(self) -> bool:
        return False

    def needs_rollover(self) -> bool:
        return True

    async def freeze(self, live_state: dict[str, object], *, notice_text: str = "") -> None:
        self.frozen_with = (live_state, notice_text)


class _NewStreamingSession(_DummyStreamingSession):
    def __init__(self) -> None:
        super().__init__()
        self.started_route: dict[str, str] | None = None
        self.updated_snapshot: dict[str, object] | None = None

    def is_active(self) -> bool:
        return True

    async def start(self, receive_id: str, *, reply_to_message_id: str = "", root_id: str = "") -> None:
        self.started_route = {
            "receive_id": receive_id,
            "reply_to_message_id": reply_to_message_id,
            "root_id": root_id,
        }

    def message_id(self) -> str:
        return "om_new_stream"

    def message_alias_ids(self) -> tuple[str, ...]:
        return ("om_new_stream",)

    async def update(self, snapshot: dict[str, object]) -> None:
        self.updated_snapshot = snapshot


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
        reply_final=lambda message, text, streaming, live_state, **kwargs: asyncio.sleep(0),
        live_turn_presenter=None,
        binding_store=None,
        runtime_service=None,
    )


def _build_runtime_context_with_stream_factory(
    tmp_path: Path,
    sessions: list[_NewStreamingSession],
) -> TurnRuntimeContext:
    runtime = _build_runtime_context(tmp_path)

    def factory(_current_messenger: object) -> _NewStreamingSession:
        session = _NewStreamingSession()
        sessions.append(session)
        return session

    return TurnRuntimeContext(
        config=runtime.config,
        store=runtime.store,
        messenger=runtime.messenger,
        typing_manager=runtime.typing_manager,
        session_ux=runtime.session_ux,
        streaming_session_factory=factory,
        execution_coordinator=runtime.execution_coordinator,
        build_card_action_context=runtime.build_card_action_context,
        streaming_route_for_message=runtime.streaming_route_for_message,
        root_id_for_message=runtime.root_id_for_message,
        is_card_action_message=runtime.is_card_action_message,
        build_session_key=runtime.build_session_key,
        remember_outbound_aliases=runtime.remember_outbound_aliases,
        reply_final=runtime.reply_final,
        trace_recorder=runtime.trace_recorder,
        live_turn_presenter=runtime.live_turn_presenter,
        binding_store=runtime.binding_store,
        runtime_service=runtime.runtime_service,
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
    runtime = _build_runtime_context(tmp_path)
    turn = TurnRunController(runtime, _build_message(), "session:session_1", LiveTurnPresenter())
    turn.initialize(_build_session(tmp_path))
    streaming = _DummyStreamingSession()
    turn.state.streaming = streaming
    turn.state.live_state["partial_text"] = "still streaming"
    turn.state.pending_streaming_states.append({"partial_text": "stale"})
    turn.state.spinner_task = asyncio.create_task(asyncio.sleep(60))

    await turn.cancel("interrupted by /stop")
    turn.request_streaming_update()
    await asyncio.sleep(0)

    assert turn.state.cancel_event.is_set() is True
    assert turn.state.spinner_task is None
    assert list(turn.state.pending_streaming_states) == []
    assert turn.state.streaming_update_event.is_set() is False
    assert streaming.closed_with is not None
    assert "已停止当前回复。" in str(streaming.closed_with)


@pytest.mark.asyncio
async def test_spinner_only_change_does_not_roll_over_streaming_card(tmp_path: Path) -> None:
    created_sessions: list[_NewStreamingSession] = []
    runtime = _build_runtime_context_with_stream_factory(tmp_path, created_sessions)
    turn = TurnRunController(runtime, _build_message(), "session:session_1", LiveTurnPresenter())
    turn.initialize(_build_session(tmp_path))
    turn.state.streaming = _RolloverStreamingSession()
    baseline_snapshot = {
        "history_items": [
            {
                "type": "command",
                "state": "running",
                "title": "Running shell command",
                "command": "pytest -q",
            }
        ],
        "spinner_frame": 0,
    }
    turn.state.last_live_text = turn.renderer.build_streaming_content(baseline_snapshot)
    turn.state.last_stable_live_text = turn.renderer.build_streaming_content(baseline_snapshot)

    await turn.update_streaming({**baseline_snapshot, "spinner_frame": 1})

    assert created_sessions == []
    assert turn.state.streaming is not None


@pytest.mark.asyncio
async def test_substantive_change_after_freeze_rolls_over_streaming_card(tmp_path: Path) -> None:
    created_sessions: list[_NewStreamingSession] = []
    runtime = _build_runtime_context_with_stream_factory(tmp_path, created_sessions)
    turn = TurnRunController(runtime, _build_message(), "session:session_1", LiveTurnPresenter())
    turn.initialize(_build_session(tmp_path))
    previous_streaming = _RolloverStreamingSession()
    turn.state.streaming = previous_streaming
    baseline_snapshot = {
        "history_items": [
            {
                "type": "command",
                "state": "running",
                "title": "Running shell command",
                "command": "pytest -q",
            }
        ],
        "spinner_frame": 0,
    }
    turn.state.last_live_text = turn.renderer.build_streaming_content(baseline_snapshot)
    turn.state.last_stable_live_text = turn.renderer.build_streaming_content(baseline_snapshot)

    await turn.update_streaming(
        {
            **baseline_snapshot,
            "spinner_frame": 1,
            "partial_text": "新的正文",
        }
    )

    assert len(created_sessions) == 1
    assert previous_streaming.frozen_with is not None
    assert turn.state.streaming is created_sessions[0]
