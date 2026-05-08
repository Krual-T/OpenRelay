"""Codex app-server adapter v2.

JSON-RPC layer + typed server notifications/requests + thread routing + event buffering
+ connection management (client/session/pool).
"""

from .app_events import (
    AppServerDisconnectedEvent,
    AppServerEvent,
    AppServerEventDecodeError,
    AppServerLaggedEvent,
    AppServerServerNotificationEvent,
    AppServerServerRequestEvent,
    parse_app_server_event,
)
from .jsonrpc import (
    JSONRPCDecodeError,
    JSONRPCError,
    JSONRPCErrorError,
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
    parse_jsonrpc_message,
    serialize_jsonrpc_message,
)
from .notifications import (
    AgentMessageDeltaNotification,
    ItemCompletedNotification,
    ServerNotification,
    ServerNotificationDecodeError,
    TurnCompletedNotification,
    TurnStartedNotification,
    parse_server_notification,
)
from .requests import (
    ServerRequest,
    ServerRequestDecodeError,
    ServerRequestPayload,
    ServerResponse,
    parse_server_request,
)
from .routing import (
    ServerNotificationThreadTarget,
    ThreadId,
    app_server_event_target,
)
from .client import CodexV2Client, CodexV2ClientError, ConnectionClosedError
from .pool import ConnectionPool, PoolFullError
from .session import CodexV2Session
from .thread_events import (
    FeedbackThreadEvent,
    ThreadBufferedEvent,
    ThreadEventSnapshot,
    ThreadEventStore,
)

__all__ = [
    # jsonrpc
    "JSONRPCDecodeError",
    "JSONRPCError",
    "JSONRPCErrorError",
    "JSONRPCMessage",
    "JSONRPCNotification",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "parse_jsonrpc_message",
    "serialize_jsonrpc_message",
    # notifications
    "AgentMessageDeltaNotification",
    "ItemCompletedNotification",
    "ServerNotification",
    "ServerNotificationDecodeError",
    "TurnCompletedNotification",
    "TurnStartedNotification",
    "parse_server_notification",
    # requests
    "ServerRequest",
    "ServerRequestDecodeError",
    "ServerRequestPayload",
    "ServerResponse",
    "parse_server_request",
    # app_events
    "AppServerDisconnectedEvent",
    "AppServerEvent",
    "AppServerEventDecodeError",
    "AppServerLaggedEvent",
    "AppServerServerNotificationEvent",
    "AppServerServerRequestEvent",
    "parse_app_server_event",
    # routing
    "ServerNotificationThreadTarget",
    "ThreadId",
    "app_server_event_target",
    # thread_events
    "FeedbackThreadEvent",
    "ThreadBufferedEvent",
    "ThreadEventSnapshot",
    "ThreadEventStore",
    # client
    "CodexV2Client",
    "CodexV2ClientError",
    "ConnectionClosedError",
    # session
    "CodexV2Session",
    # pool
    "ConnectionPool",
    "PoolFullError",
]
