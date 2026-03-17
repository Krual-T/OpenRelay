from openrelay.agent_runtime import (
    ApprovalDecision,
    ApprovalRequestedEvent,
    ApprovalResolvedEvent,
    AssistantCompletedEvent,
    AssistantDeltaEvent,
    BackendNoticeEvent,
    PlanUpdatedEvent,
    ReasoningDeltaEvent,
    ToolCompletedEvent,
    ToolProgressEvent,
    ToolStartedEvent,
    TurnCompletedEvent,
    TurnStartedEvent,
    UsageUpdatedEvent,
)
from openrelay.backends.codex_adapter import CodexProtocolMapper, CodexTurnState


def test_codex_mapper_maps_turn_started_and_alias_agent_delta() -> None:
    mapper = CodexProtocolMapper(session_id="relay-1", native_session_id="thread_1")
    state = CodexTurnState()

    started = mapper.map_notification("turn/started", {"threadId": "thread_1", "turn": {"id": "turn_1"}}, state)
    direct = mapper.map_notification(
        "item/agentMessage/delta",
        {"threadId": "thread_1", "turnId": "turn_1", "itemId": "msg_1", "delta": "hello"},
        state,
    )
    alias = mapper.map_notification(
        "codex/event/agent_message_content_delta",
        {
            "conversationId": "thread_1",
            "id": "turn_1",
            "msg": {"thread_id": "thread_1", "turn_id": "turn_1", "item_id": "msg_1", "delta": "hello"},
        },
        state,
    )

    assert len(started) == 1 and isinstance(started[0], TurnStartedEvent)
    assert len(direct) == 1 and isinstance(direct[0], AssistantDeltaEvent)
    assert direct[0].delta == "hello"
    assert len(alias) == 1 and isinstance(alias[0], BackendNoticeEvent)
    assert alias[0].provider_payload["classification"] == "observe"


def test_codex_mapper_aggregates_reasoning_and_prefers_summary() -> None:
    mapper = CodexProtocolMapper(session_id="relay-1", native_session_id="thread_1", turn_id="turn_1")
    state = CodexTurnState()

    delta = mapper.map_notification(
        "item/reasoning/textDelta",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "itemId": "reasoning_1",
            "contentIndex": 0,
            "delta": "verbose trace",
        },
        state,
    )
    alias = mapper.map_notification(
        "codex/event/reasoning_content_delta",
        {
            "conversationId": "thread_1",
            "id": "turn_1",
            "msg": {
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "item_id": "reasoning_1",
                "content_index": 0,
                "delta": "verbose trace",
            },
        },
        state,
    )
    completed = mapper.map_notification(
        "item/completed",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "item": {
                "id": "reasoning_1",
                "type": "reasoning",
                "summary": ["concise summary"],
                "content": ["verbose trace"],
            },
        },
        state,
    )

    assert len(delta) == 1 and isinstance(delta[0], ReasoningDeltaEvent)
    assert delta[0].text == "verbose trace"
    assert len(alias) == 1 and isinstance(alias[0], BackendNoticeEvent)
    assert alias[0].provider_payload["classification"] == "observe"
    assert len(completed) == 1 and isinstance(completed[0], ReasoningDeltaEvent)
    assert completed[0].text == "concise summary"


def test_codex_mapper_maps_tool_lifecycle_and_usage() -> None:
    mapper = CodexProtocolMapper(session_id="relay-1", native_session_id="thread_1", turn_id="turn_1")
    state = CodexTurnState()

    started = mapper.map_notification(
        "item/started",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "item": {"id": "cmd_1", "type": "commandExecution", "command": "rg runtime"},
        },
        state,
    )
    progress = mapper.map_notification(
        "item/commandExecution/outputDelta",
        {"threadId": "thread_1", "turnId": "turn_1", "itemId": "cmd_1", "delta": "src/openrelay/runtime\n"},
        state,
    )
    completed = mapper.map_notification(
        "item/completed",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "item": {
                "id": "cmd_1",
                "type": "commandExecution",
                "command": "rg runtime",
                "aggregatedOutput": "src/openrelay/runtime\n",
                "exitCode": 0,
            },
        },
        state,
    )
    usage = mapper.map_notification(
        "thread/tokenUsage/updated",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "tokenUsage": {
                "last": {"inputTokens": 10, "cachedInputTokens": 2, "outputTokens": 4, "reasoningOutputTokens": 1, "totalTokens": 14},
                "modelContextWindow": 200000,
            },
        },
        state,
    )

    assert len(started) == 1 and isinstance(started[0], ToolStartedEvent)
    assert started[0].tool.kind == "command"
    assert len(progress) == 1 and isinstance(progress[0], ToolProgressEvent)
    assert progress[0].detail == "src/openrelay/runtime\n"
    assert len(completed) == 1 and isinstance(completed[0], ToolCompletedEvent)
    assert completed[0].tool.exit_code == 0
    assert completed[0].tool.detail == "src/openrelay/runtime\n"
    assert len(usage) == 1 and isinstance(usage[0], UsageUpdatedEvent)
    assert usage[0].usage.total_tokens == 14
    assert usage[0].usage.context_window == 200000


def test_codex_mapper_maps_server_request_and_resolution() -> None:
    mapper = CodexProtocolMapper(session_id="relay-1", native_session_id="thread_1", turn_id="turn_1")
    state = CodexTurnState()

    requested = mapper.map_server_request(
        42,
        "item/commandExecution/requestApproval",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "command": "pytest -q",
            "cwd": "/repo",
            "reason": "Run validation",
        },
    )
    resolved = mapper.map_notification(
        "serverRequest/resolved",
        {"threadId": "thread_1", "turnId": "turn_1", "requestId": "42"},
        state,
    )
    response = mapper.build_approval_response(
        requested.request,
        ApprovalDecision(decision="accept_for_session"),
    )

    assert isinstance(requested, ApprovalRequestedEvent)
    assert requested.request.kind == "command"
    assert requested.request.options == ("accept", "accept_for_session", "decline", "cancel")
    assert "pytest -q" in requested.request.description
    assert requested.request.payload["command"] == "pytest -q"
    assert requested.request.payload["cwd"] == "/repo"
    assert len(resolved) == 1 and isinstance(resolved[0], ApprovalResolvedEvent)
    assert resolved[0].approval_id == "42"
    assert response == {"decision": "acceptForSession"}


def test_codex_mapper_maps_terminal_turn_outcomes() -> None:
    mapper = CodexProtocolMapper(session_id="relay-1", native_session_id="thread_1", turn_id="turn_1")
    state = CodexTurnState()

    mapper.map_notification(
        "item/completed",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "item": {"id": "msg_1", "type": "agentMessage", "text": "done"},
        },
        state,
    )
    completed = mapper.map_notification(
        "turn/completed",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "turn": {"status": "completed"},
        },
        state,
    )
    failed = mapper.map_notification(
        "error",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "error": {"message": "boom"},
            "willRetry": False,
        },
        state,
    )

    assert len(completed) == 1 and isinstance(completed[0], TurnCompletedEvent)
    assert completed[0].final_text == "done"
    assert failed == ()


def test_codex_mapper_maps_structured_plan_update() -> None:
    mapper = CodexProtocolMapper(session_id="relay-1", native_session_id="thread_1", turn_id="turn_1")
    state = CodexTurnState()

    events = mapper.map_notification(
        "turn/plan/updated",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "plan": [
                {"step": "Inspect runtime", "status": "completed"},
                {"step": "Wire mapper", "status": "in_progress"},
            ],
            "explanation": "phase 1",
        },
        state,
    )

    assert len(events) == 1 and isinstance(events[0], PlanUpdatedEvent)
    assert [step.step for step in events[0].steps] == ["Inspect runtime", "Wire mapper"]
    assert [step.status for step in events[0].steps] == ["completed", "in_progress"]
    assert events[0].explanation == "phase 1"


def test_codex_mapper_ignores_typed_user_message_items() -> None:
    mapper = CodexProtocolMapper(session_id="relay-1", native_session_id="thread_1", turn_id="turn_1")
    state = CodexTurnState()

    started = mapper.map_notification(
        "item/started",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "item": {"id": "user_1", "type": "userMessage", "content": [{"type": "text", "text": "hello"}]},
        },
        state,
    )
    completed = mapper.map_notification(
        "item/completed",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "item": {"id": "user_1", "type": "userMessage", "content": [{"type": "text", "text": "hello"}]},
        },
        state,
    )

    assert started == ()
    assert completed == ()


def test_codex_mapper_records_typed_system_snapshots() -> None:
    mapper = CodexProtocolMapper(session_id="relay-1", native_session_id="thread_1", turn_id="turn_1")
    state = CodexTurnState()

    rate_limits = mapper.map_notification(
        "account/rateLimits/updated",
        {
            "rateLimits": {
                "limitId": "codex",
                "primary": {"usedPercent": 37},
            }
        },
        state,
    )
    thread_status = mapper.map_notification(
        "thread/status/changed",
        {
            "threadId": "thread_1",
            "status": {"type": "active", "activeFlags": []},
        },
        state,
    )

    assert rate_limits == ()
    assert thread_status == ()
    assert state.system_snapshot["thread_status"] == "active"
    assert state.system_snapshot["rate_limits_payload"]["limitId"] == "codex"


def test_codex_mapper_maps_assistant_completed_event() -> None:
    mapper = CodexProtocolMapper(session_id="relay-1", native_session_id="thread_1", turn_id="turn_1")
    state = CodexTurnState()

    events = mapper.map_notification(
        "item/completed",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "item": {"id": "msg_1", "type": "agentMessage", "text": "final answer"},
        },
        state,
    )

    assert len(events) == 1 and isinstance(events[0], AssistantCompletedEvent)
    assert events[0].text == "final answer"


def test_codex_mapper_falls_back_for_unexpected_backend_event() -> None:
    mapper = CodexProtocolMapper(session_id="relay-1", native_session_id="thread_1", turn_id="turn_1")
    state = CodexTurnState()

    events = mapper.map_notification(
        "item/unknownEvent",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "foo": "bar",
        },
        state,
    )

    assert len(events) == 1 and isinstance(events[0], BackendNoticeEvent)
    assert events[0].provider_payload["fallback"] is True
    assert events[0].provider_payload["raw_event"]["params"]["foo"] == "bar"


def test_codex_mapper_falls_back_for_unexpected_item_type() -> None:
    mapper = CodexProtocolMapper(session_id="relay-1", native_session_id="thread_1", turn_id="turn_1")
    state = CodexTurnState()

    events = mapper.map_notification(
        "item/started",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "item": {"id": "mystery_1", "type": "customTool", "foo": "bar"},
        },
        state,
    )

    assert len(events) == 1 and isinstance(events[0], BackendNoticeEvent)
    assert events[0].provider_payload["fallback"] is True
    assert events[0].provider_payload["raw_event"]["item"]["type"] == "customTool"
