from __future__ import annotations

import pytest

from openrelay.backends.codex_adapter_v2.app_events import (
    AppServerDisconnectedEvent,
    AppServerLaggedEvent,
    AppServerServerNotificationEvent,
    AppServerServerRequestEvent,
)
from openrelay.backends.codex_adapter_v2.notifications import (
    AgentMessageDeltaNotification,
    ServerNotification,
    TurnStartedNotification,
)
from openrelay.backends.codex_adapter_v2.requests import ServerRequest
from openrelay.backends.codex_adapter_v2.routing import (
    ServerNotificationThreadTarget,
    ThreadId,
    app_server_event_target,
    server_notification_thread_target,
    server_request_thread_id,
)

THREAD_ID = "00000000-0000-0000-0000-000000000011"


def test_thread_id_accepts_only_uuid_strings() -> None:
    assert ThreadId.from_string(THREAD_ID) == ThreadId(THREAD_ID)

    with pytest.raises(ValueError, match="invalid thread id"):
        ThreadId.from_string("thread_1")


def test_thread_started_notification_uses_nested_thread_id() -> None:
    notification = ServerNotification(
        variant="ThreadStarted",
        method="thread/started",
        params={"thread": {"id": THREAD_ID}},
    )

    assert server_notification_thread_target(notification) == ServerNotificationThreadTarget.thread(THREAD_ID)


def test_typed_notification_uses_thread_id_attribute() -> None:
    notification = ServerNotification(
        variant="AgentMessageDelta",
        method="item/agentMessage/delta",
        params=AgentMessageDeltaNotification(
            thread_id=THREAD_ID,
            turn_id="turn_1",
            item_id="item_1",
            delta="你好",
        ),
    )

    assert server_notification_thread_target(notification) == ServerNotificationThreadTarget.thread(THREAD_ID)


def test_warning_notification_without_thread_is_global_and_with_thread_routes_to_thread() -> None:
    assert server_notification_thread_target(
        ServerNotification(variant="Warning", method="warning", params={"message": "heads up"})
    ) == ServerNotificationThreadTarget.global_()

    assert server_notification_thread_target(
        ServerNotification(
            variant="Warning",
            method="warning",
            params={"threadId": THREAD_ID, "message": "heads up"},
        )
    ) == ServerNotificationThreadTarget.thread(THREAD_ID)


def test_invalid_notification_thread_id_is_reported() -> None:
    notification = ServerNotification(
        variant="TurnStarted",
        method="turn/started",
        params=TurnStartedNotification(
            thread_id="thread_1",
            turn={"id": "turn_1", "status": "inProgress"},
        ),
    )

    assert server_notification_thread_target(notification) == ServerNotificationThreadTarget.invalid("thread_1")


@pytest.mark.parametrize(
    "variant",
    [
        "SkillsChanged",
        "McpServerStatusUpdated",
        "McpServerOauthLoginCompleted",
        "AccountUpdated",
        "AccountRateLimitsUpdated",
        "AppListUpdated",
        "RemoteControlStatusChanged",
        "ExternalAgentConfigImportCompleted",
        "DeprecationNotice",
        "ConfigWarning",
        "FuzzyFileSearchSessionUpdated",
        "FuzzyFileSearchSessionCompleted",
        "CommandExecOutputDelta",
        "ProcessOutputDelta",
        "ProcessExited",
        "FsChanged",
        "WindowsWorldWritableWarning",
        "WindowsSandboxSetupCompleted",
        "AccountLoginCompleted",
    ],
)
def test_official_global_notifications_route_to_global(variant: str) -> None:
    notification = ServerNotification(variant=variant, method="method", params={})

    assert server_notification_thread_target(notification) == ServerNotificationThreadTarget.global_()


@pytest.mark.parametrize(
    "variant",
    [
        "CommandExecutionRequestApproval",
        "FileChangeRequestApproval",
        "ToolRequestUserInput",
        "McpServerElicitationRequest",
        "PermissionsRequestApproval",
        "DynamicToolCall",
    ],
)
def test_thread_server_requests_use_thread_id_param(variant: str) -> None:
    request = ServerRequest(
        variant=variant,
        method="method",
        request_id=1,
        params={"threadId": THREAD_ID},
    )

    assert server_request_thread_id(request) == ThreadId(THREAD_ID)


@pytest.mark.parametrize(
    "variant",
    ["ChatgptAuthTokensRefresh", "ApplyPatchApproval", "ExecCommandApproval"],
)
def test_global_server_requests_have_no_thread_id(variant: str) -> None:
    request = ServerRequest(variant=variant, method="method", request_id=1, params={"threadId": THREAD_ID})

    assert server_request_thread_id(request) is None


def test_app_server_event_target_routes_notification_request_and_global_events() -> None:
    notification = ServerNotification(
        variant="AgentMessageDelta",
        method="item/agentMessage/delta",
        params=AgentMessageDeltaNotification(
            thread_id=THREAD_ID,
            turn_id="turn_1",
            item_id="item_1",
            delta="你好",
        ),
    )
    request = ServerRequest(
        variant="DynamicToolCall",
        method="item/tool/call",
        request_id=1,
        params={"threadId": THREAD_ID},
    )

    assert app_server_event_target(AppServerServerNotificationEvent(notification)) == ServerNotificationThreadTarget.thread(
        THREAD_ID
    )
    assert app_server_event_target(AppServerServerRequestEvent(request)) == ServerNotificationThreadTarget.thread(
        THREAD_ID
    )
    assert app_server_event_target(AppServerLaggedEvent(skipped=3)) == ServerNotificationThreadTarget.global_()
    assert app_server_event_target(AppServerDisconnectedEvent(message="closed")) == ServerNotificationThreadTarget.global_()
