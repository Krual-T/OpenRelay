from __future__ import annotations

import pytest

from openrelay.backends.codex_adapter_v2.jsonrpc import JSONRPCNotification, JSONRPCRequest
from openrelay.backends.codex_adapter_v2.notifications import (
    AgentMessageDeltaNotification,
    ItemCompletedNotification,
    ServerNotification,
    ServerNotificationDecodeError,
    TurnCompletedNotification,
    TurnStartedNotification,
    parse_server_notification,
)


def test_agent_message_delta_notification_uses_official_wire_method() -> None:
    event = parse_server_notification(
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

    assert event == ServerNotification(
        variant="AgentMessageDelta",
        method="item/agentMessage/delta",
        params=AgentMessageDeltaNotification(
            thread_id="thread_1",
            turn_id="turn_1",
            item_id="item_1",
            delta="你好",
        ),
    )


def test_turn_and_item_lifecycle_notifications_keep_payload_objects() -> None:
    turn = {"id": "turn_1", "status": "inProgress", "items": []}
    item = {"type": "agentMessage", "id": "item_1", "text": "你好"}

    assert parse_server_notification(
        JSONRPCNotification(method="turn/started", params={"threadId": "thread_1", "turn": turn})
    ) == ServerNotification(
        variant="TurnStarted",
        method="turn/started",
        params=TurnStartedNotification(thread_id="thread_1", turn=turn),
    )
    assert parse_server_notification(
        JSONRPCNotification(
            method="item/completed",
            params={
                "threadId": "thread_1",
                "turnId": "turn_1",
                "item": item,
                "completedAtMs": 1778220000000,
            },
        )
    ) == ServerNotification(
        variant="ItemCompleted",
        method="item/completed",
        params=ItemCompletedNotification(
            thread_id="thread_1",
            turn_id="turn_1",
            item=item,
            completed_at_ms=1778220000000,
        ),
    )
    assert parse_server_notification(
        JSONRPCNotification(method="turn/completed", params={"threadId": "thread_1", "turn": turn})
    ) == ServerNotification(
        variant="TurnCompleted",
        method="turn/completed",
        params=TurnCompletedNotification(thread_id="thread_1", turn=turn),
    )


def test_known_notification_without_specific_payload_model_keeps_raw_params() -> None:
    event = parse_server_notification(
        JSONRPCNotification(method="warning", params={"message": "low context window"})
    )

    assert event == ServerNotification(
        variant="Warning",
        method="warning",
        params={"message": "low context window"},
    )


def test_unknown_notification_is_ignored_like_official_client() -> None:
    assert parse_server_notification(JSONRPCNotification(method="future/event", params={})) is None


def test_non_notification_message_is_rejected() -> None:
    with pytest.raises(TypeError, match="JSONRPCNotification"):
        parse_server_notification(JSONRPCRequest(id=1, method="thread/list"))


def test_invalid_supported_notification_payload_is_rejected() -> None:
    with pytest.raises(ServerNotificationDecodeError, match="threadId"):
        parse_server_notification(
            JSONRPCNotification(
                method="item/agentMessage/delta",
                params={"turnId": "turn_1", "itemId": "item_1", "delta": "你好"},
            )
        )
