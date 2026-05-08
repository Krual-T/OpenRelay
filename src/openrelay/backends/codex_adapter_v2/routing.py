from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from .app_events import (
    AppServerDisconnectedEvent,
    AppServerEvent,
    AppServerLaggedEvent,
    AppServerServerNotificationEvent,
    AppServerServerRequestEvent,
)
from .notifications import (
    AgentMessageDeltaNotification,
    ItemCompletedNotification,
    ServerNotification,
    TurnCompletedNotification,
    TurnStartedNotification,
)
from .requests import ServerRequest


@dataclass(frozen=True, slots=True)
class ThreadId:
    value: str

    @classmethod
    def from_string(cls, value: str) -> ThreadId:
        try:
            parsed = UUID(value)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid thread id `{value}`") from exc
        return cls(str(parsed))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ServerNotificationThreadTarget:
    kind: Literal["Thread", "InvalidThreadId", "Global"]
    thread_id: ThreadId | None = None
    invalid_thread_id: str | None = None

    @classmethod
    def thread(cls, thread_id: str | ThreadId) -> ServerNotificationThreadTarget:
        if isinstance(thread_id, ThreadId):
            return cls(kind="Thread", thread_id=thread_id)
        return cls(kind="Thread", thread_id=ThreadId.from_string(thread_id))

    @classmethod
    def invalid(cls, thread_id: str) -> ServerNotificationThreadTarget:
        return cls(kind="InvalidThreadId", invalid_thread_id=thread_id)

    @classmethod
    def global_(cls) -> ServerNotificationThreadTarget:
        return cls(kind="Global")


_GLOBAL_NOTIFICATION_VARIANTS = {
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
}

_THREAD_REQUEST_VARIANTS = {
    "CommandExecutionRequestApproval",
    "FileChangeRequestApproval",
    "ToolRequestUserInput",
    "McpServerElicitationRequest",
    "PermissionsRequestApproval",
    "DynamicToolCall",
}


def server_request_thread_id(request: ServerRequest) -> ThreadId | None:
    if request.variant not in _THREAD_REQUEST_VARIANTS:
        return None
    thread_id = request.params.get("threadId")
    if not isinstance(thread_id, str):
        return None
    try:
        return ThreadId.from_string(thread_id)
    except ValueError:
        return None


def server_notification_thread_target(
    notification: ServerNotification,
) -> ServerNotificationThreadTarget:
    thread_id = _notification_thread_id(notification)
    if thread_id is None:
        return ServerNotificationThreadTarget.global_()
    try:
        return ServerNotificationThreadTarget.thread(thread_id)
    except ValueError:
        return ServerNotificationThreadTarget.invalid(thread_id)


def app_server_event_target(event: AppServerEvent) -> ServerNotificationThreadTarget:
    if isinstance(event, AppServerServerNotificationEvent):
        return server_notification_thread_target(event.notification)
    if isinstance(event, AppServerServerRequestEvent):
        thread_id = server_request_thread_id(event.request)
        if thread_id is None:
            return ServerNotificationThreadTarget.global_()
        return ServerNotificationThreadTarget.thread(thread_id)
    if isinstance(event, (AppServerLaggedEvent, AppServerDisconnectedEvent)):
        return ServerNotificationThreadTarget.global_()
    raise TypeError(f"unsupported app-server event: {event!r}")


def _notification_thread_id(notification: ServerNotification) -> str | None:
    if notification.variant in _GLOBAL_NOTIFICATION_VARIANTS:
        return None
    if isinstance(notification.params, AgentMessageDeltaNotification):
        return notification.params.thread_id
    if isinstance(notification.params, TurnStartedNotification):
        return notification.params.thread_id
    if isinstance(notification.params, TurnCompletedNotification):
        return notification.params.thread_id
    if isinstance(notification.params, ItemCompletedNotification):
        return notification.params.thread_id
    params = notification.params
    if notification.variant == "ThreadStarted":
        thread = params.get("thread")
        if isinstance(thread, dict):
            thread_id = thread.get("id")
            return thread_id if isinstance(thread_id, str) else None
        return None
    thread_id = params.get("threadId")
    if isinstance(thread_id, str):
        return thread_id
    return None
