from __future__ import annotations

import pytest

from openrelay.backends.codex_adapter_v2.app_events import (
    AppServerDisconnectedEvent,
    AppServerEventDecodeError,
    AppServerLaggedEvent,
    AppServerServerNotificationEvent,
    AppServerServerRequestEvent,
    app_server_event_from_notification,
    app_server_event_from_request,
    event_requires_delivery,
    parse_app_server_event,
    server_notification_requires_delivery,
)
from openrelay.backends.codex_adapter_v2.jsonrpc import (
    JSONRPCError,
    JSONRPCErrorError,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
)
from openrelay.backends.codex_adapter_v2.notifications import (
    AgentMessageDeltaNotification,
    ServerNotification,
    TurnCompletedNotification,
)
from openrelay.backends.codex_adapter_v2.requests import ServerRequest


def test_app_server_event_variants_have_official_payload_attributes() -> None:
    notification = ServerNotification(
        variant="AgentMessageDelta",
        method="item/agentMessage/delta",
        params=AgentMessageDeltaNotification(
            thread_id="thread_1",
            turn_id="turn_1",
            item_id="item_1",
            delta="你好",
        ),
    )
    request = ServerRequest(
        variant="ExecCommandApproval",
        method="execCommandApproval",
        request_id=3,
        params={"command": "pytest"},
    )

    assert AppServerLaggedEvent(skipped=2).skipped == 2
    assert AppServerServerNotificationEvent(notification=notification).notification == notification
    assert AppServerServerRequestEvent(request=request).request == request
    assert AppServerDisconnectedEvent(message="closed").message == "closed"


def test_notification_message_becomes_app_server_notification_event() -> None:
    event = parse_app_server_event(
        JSONRPCNotification(
            method="item/agentMessage/delta",
            params={
                "threadId": "thread_1",
                "turnId": "turn_1",
                "itemId": "item_1",
                "delta": "你好",
            },
        )
    )

    assert event == AppServerServerNotificationEvent(
        notification=ServerNotification(
            variant="AgentMessageDelta",
            method="item/agentMessage/delta",
            params=AgentMessageDeltaNotification(
                thread_id="thread_1",
                turn_id="turn_1",
                item_id="item_1",
                delta="你好",
            ),
        )
    )


def test_request_message_becomes_app_server_request_event() -> None:
    event = parse_app_server_event(
        JSONRPCRequest(
            id="request_1",
            method="mcpServer/elicitation/request",
            params={"threadId": "thread_1", "serverName": "demo"},
        )
    )

    assert event == AppServerServerRequestEvent(
        request=ServerRequest(
            variant="McpServerElicitationRequest",
            method="mcpServer/elicitation/request",
            request_id="request_1",
            params={"threadId": "thread_1", "serverName": "demo"},
        )
    )


def test_unknown_notification_is_not_an_app_server_event() -> None:
    assert parse_app_server_event(JSONRPCNotification(method="future/event", params={})) is None


def test_response_and_error_messages_are_not_app_server_events() -> None:
    assert parse_app_server_event(JSONRPCResponse(id=1, result={})) is None
    assert parse_app_server_event(JSONRPCError(id=1, error=JSONRPCErrorError(code=-1, message="x"))) is None


def test_unknown_request_raises_app_server_event_decode_error() -> None:
    with pytest.raises(AppServerEventDecodeError, match="unsupported server request"):
        parse_app_server_event(JSONRPCRequest(id=1, method="future/request", params={}))


def test_convenience_wrappers_match_official_conversion_helpers() -> None:
    notification = JSONRPCNotification(
        method="turn/completed",
        params={"threadId": "thread_1", "turn": {"id": "turn_1", "status": "completed"}},
    )
    request = JSONRPCRequest(id=9, method="account/chatgptAuthTokens/refresh", params={})

    assert app_server_event_from_notification(notification) == parse_app_server_event(notification)
    assert app_server_event_from_request(request) == parse_app_server_event(request)


@pytest.mark.parametrize(
    ("variant", "expected"),
    [
        ("TurnCompleted", True),
        ("ItemCompleted", True),
        ("AgentMessageDelta", True),
        ("PlanDelta", True),
        ("ReasoningSummaryTextDelta", True),
        ("ReasoningTextDelta", True),
        ("CommandExecutionOutputDelta", False),
        ("Warning", False),
    ],
)
def test_server_notification_requires_delivery_matches_official_lossless_tier(
    variant: str,
    expected: bool,
) -> None:
    params = (
        TurnCompletedNotification(thread_id="thread_1", turn={"id": "turn_1", "status": "completed"})
        if variant == "TurnCompleted"
        else {}
    )
    notification = ServerNotification(
        variant=variant,
        method="method",
        params=params,
    )

    assert server_notification_requires_delivery(notification) is expected
    assert event_requires_delivery(AppServerServerNotificationEvent(notification)) is expected


def test_non_notification_app_server_events_do_not_require_delivery() -> None:
    assert event_requires_delivery(AppServerLaggedEvent(skipped=1)) is False
    assert event_requires_delivery(AppServerDisconnectedEvent(message="closed")) is False
    assert event_requires_delivery(
        AppServerServerRequestEvent(
            request=ServerRequest(
                variant="ExecCommandApproval",
                method="execCommandApproval",
                request_id=1,
                params={},
            )
        )
    ) is False
