from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .jsonrpc import (
    JSONRPCError,
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
)
from .notifications import ServerNotification, parse_server_notification
from .requests import ServerRequest, ServerRequestDecodeError, parse_server_request


class AppServerEventDecodeError(ValueError):
    """Raised when a JSON-RPC message cannot become a supported app-server event."""


@dataclass(frozen=True, slots=True)
class AppServerLaggedEvent:
    skipped: int


@dataclass(frozen=True, slots=True)
class AppServerServerNotificationEvent:
    notification: ServerNotification


@dataclass(frozen=True, slots=True)
class AppServerServerRequestEvent:
    request: ServerRequest


@dataclass(frozen=True, slots=True)
class AppServerDisconnectedEvent:
    message: str


AppServerEvent: TypeAlias = (
    AppServerLaggedEvent
    | AppServerServerNotificationEvent
    | AppServerServerRequestEvent
    | AppServerDisconnectedEvent
)

_LOSSLESS_SERVER_NOTIFICATION_VARIANTS = {
    "TurnCompleted",
    "ItemCompleted",
    "AgentMessageDelta",
    "PlanDelta",
    "ReasoningSummaryTextDelta",
    "ReasoningTextDelta",
}


def parse_app_server_event(message: JSONRPCMessage) -> AppServerEvent | None:
    if isinstance(message, JSONRPCNotification):
        return app_server_event_from_notification(message)
    if isinstance(message, JSONRPCRequest):
        return app_server_event_from_request(message)
    if isinstance(message, (JSONRPCResponse, JSONRPCError)):
        return None
    raise TypeError(f"unsupported JSON-RPC message: {message!r}")


def app_server_event_from_notification(
    message: JSONRPCNotification,
) -> AppServerServerNotificationEvent | None:
    notification = parse_server_notification(message)
    if notification is None:
        return None
    return AppServerServerNotificationEvent(notification=notification)


def app_server_event_from_request(message: JSONRPCRequest) -> AppServerServerRequestEvent:
    try:
        request = parse_server_request(message)
    except ServerRequestDecodeError as exc:
        raise AppServerEventDecodeError(str(exc)) from exc
    return AppServerServerRequestEvent(request=request)


def server_notification_requires_delivery(notification: ServerNotification) -> bool:
    return notification.variant in _LOSSLESS_SERVER_NOTIFICATION_VARIANTS


def event_requires_delivery(event: AppServerEvent) -> bool:
    if isinstance(event, AppServerServerNotificationEvent):
        return server_notification_requires_delivery(event.notification)
    return False
