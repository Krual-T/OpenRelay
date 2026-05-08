from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

from .jsonrpc import JSONRPCNotification

JSONValue: TypeAlias = Any


class ServerNotificationDecodeError(ValueError):
    """Raised when a known app-server notification has an invalid payload."""


@dataclass(frozen=True, slots=True)
class AgentMessageDeltaNotification:
    thread_id: str
    turn_id: str
    item_id: str
    delta: str


@dataclass(frozen=True, slots=True)
class TurnStartedNotification:
    thread_id: str
    turn: dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class ItemCompletedNotification:
    thread_id: str
    turn_id: str
    item: dict[str, JSONValue]
    completed_at_ms: int


@dataclass(frozen=True, slots=True)
class TurnCompletedNotification:
    thread_id: str
    turn: dict[str, JSONValue]


ServerNotificationParams: TypeAlias = (
    AgentMessageDeltaNotification
    | TurnStartedNotification
    | ItemCompletedNotification
    | TurnCompletedNotification
    | dict[str, JSONValue]
)


@dataclass(frozen=True, slots=True)
class ServerNotification:
    variant: str
    method: str
    params: ServerNotificationParams


def parse_server_notification(message: JSONRPCNotification) -> ServerNotification | None:
    if not isinstance(message, JSONRPCNotification):
        raise TypeError(f"expected JSONRPCNotification, got {type(message).__name__}")
    mapper = _NOTIFICATION_MAPPERS.get(message.method)
    if mapper is not None:
        return mapper(_coerce_params(message.params))
    variant = _SERVER_NOTIFICATION_VARIANTS.get(message.method)
    if variant is None:
        return None
    return ServerNotification(
        variant=variant,
        method=message.method,
        params=dict(_coerce_params(message.params)),
    )


def _map_agent_message_delta(params: Mapping[str, JSONValue]) -> ServerNotification:
    return ServerNotification(
        variant="AgentMessageDelta",
        method="item/agentMessage/delta",
        params=AgentMessageDeltaNotification(
            thread_id=_string_field(params, "threadId"),
            turn_id=_string_field(params, "turnId"),
            item_id=_string_field(params, "itemId"),
            delta=_string_field(params, "delta"),
        ),
    )


def _map_turn_started(params: Mapping[str, JSONValue]) -> ServerNotification:
    return ServerNotification(
        variant="TurnStarted",
        method="turn/started",
        params=TurnStartedNotification(
            thread_id=_string_field(params, "threadId"),
            turn=_object_field(params, "turn"),
        ),
    )


def _map_item_completed(params: Mapping[str, JSONValue]) -> ServerNotification:
    return ServerNotification(
        variant="ItemCompleted",
        method="item/completed",
        params=ItemCompletedNotification(
            thread_id=_string_field(params, "threadId"),
            turn_id=_string_field(params, "turnId"),
            item=_object_field(params, "item"),
            completed_at_ms=_int_field(params, "completedAtMs"),
        ),
    )


def _map_turn_completed(params: Mapping[str, JSONValue]) -> ServerNotification:
    return ServerNotification(
        variant="TurnCompleted",
        method="turn/completed",
        params=TurnCompletedNotification(
            thread_id=_string_field(params, "threadId"),
            turn=_object_field(params, "turn"),
        ),
    )


_NOTIFICATION_MAPPERS: dict[str, Callable[[Mapping[str, JSONValue]], ServerNotification]] = {
    "item/agentMessage/delta": _map_agent_message_delta,
    "turn/started": _map_turn_started,
    "item/completed": _map_item_completed,
    "turn/completed": _map_turn_completed,
}


_SERVER_NOTIFICATION_VARIANTS: dict[str, str] = {
    "error": "Error",
    "thread/started": "ThreadStarted",
    "thread/status/changed": "ThreadStatusChanged",
    "thread/archived": "ThreadArchived",
    "thread/unarchived": "ThreadUnarchived",
    "thread/closed": "ThreadClosed",
    "skills/changed": "SkillsChanged",
    "thread/name/updated": "ThreadNameUpdated",
    "thread/goal/updated": "ThreadGoalUpdated",
    "thread/goal/cleared": "ThreadGoalCleared",
    "thread/tokenUsage/updated": "ThreadTokenUsageUpdated",
    "turn/started": "TurnStarted",
    "hook/started": "HookStarted",
    "turn/completed": "TurnCompleted",
    "hook/completed": "HookCompleted",
    "turn/diff/updated": "TurnDiffUpdated",
    "turn/plan/updated": "TurnPlanUpdated",
    "item/started": "ItemStarted",
    "item/autoApprovalReview/started": "ItemGuardianApprovalReviewStarted",
    "item/autoApprovalReview/completed": "ItemGuardianApprovalReviewCompleted",
    "item/completed": "ItemCompleted",
    "rawResponseItem/completed": "RawResponseItemCompleted",
    "item/agentMessage/delta": "AgentMessageDelta",
    "item/plan/delta": "PlanDelta",
    "command/exec/outputDelta": "CommandExecOutputDelta",
    "process/outputDelta": "ProcessOutputDelta",
    "process/exited": "ProcessExited",
    "item/commandExecution/outputDelta": "CommandExecutionOutputDelta",
    "item/commandExecution/terminalInteraction": "TerminalInteraction",
    "item/fileChange/outputDelta": "FileChangeOutputDelta",
    "item/fileChange/patchUpdated": "FileChangePatchUpdated",
    "serverRequest/resolved": "ServerRequestResolved",
    "item/mcpToolCall/progress": "McpToolCallProgress",
    "mcpServer/oauthLogin/completed": "McpServerOauthLoginCompleted",
    "mcpServer/startupStatus/updated": "McpServerStatusUpdated",
    "account/updated": "AccountUpdated",
    "account/rateLimits/updated": "AccountRateLimitsUpdated",
    "app/list/updated": "AppListUpdated",
    "remoteControl/status/changed": "RemoteControlStatusChanged",
    "externalAgentConfig/import/completed": "ExternalAgentConfigImportCompleted",
    "fs/changed": "FsChanged",
    "item/reasoning/summaryTextDelta": "ReasoningSummaryTextDelta",
    "item/reasoning/summaryPartAdded": "ReasoningSummaryPartAdded",
    "item/reasoning/textDelta": "ReasoningTextDelta",
    "thread/compacted": "ContextCompacted",
    "model/rerouted": "ModelRerouted",
    "model/verification": "ModelVerification",
    "warning": "Warning",
    "guardianWarning": "GuardianWarning",
    "deprecationNotice": "DeprecationNotice",
    "configWarning": "ConfigWarning",
    "fuzzyFileSearch/sessionUpdated": "FuzzyFileSearchSessionUpdated",
    "fuzzyFileSearch/sessionCompleted": "FuzzyFileSearchSessionCompleted",
    "thread/realtime/started": "ThreadRealtimeStarted",
    "thread/realtime/itemAdded": "ThreadRealtimeItemAdded",
    "thread/realtime/transcript/delta": "ThreadRealtimeTranscriptDelta",
    "thread/realtime/transcript/done": "ThreadRealtimeTranscriptDone",
    "thread/realtime/outputAudio/delta": "ThreadRealtimeOutputAudioDelta",
    "thread/realtime/sdp": "ThreadRealtimeSdp",
    "thread/realtime/error": "ThreadRealtimeError",
    "thread/realtime/closed": "ThreadRealtimeClosed",
    "windows/worldWritableWarning": "WindowsWorldWritableWarning",
    "windowsSandbox/setupCompleted": "WindowsSandboxSetupCompleted",
    "account/login/completed": "AccountLoginCompleted",
}


def _coerce_params(value: JSONValue | None) -> Mapping[str, JSONValue]:
    if isinstance(value, Mapping):
        return value
    if value is None:
        return {}
    raise ServerNotificationDecodeError(f"notification params must be an object, got {type(value).__name__}")


def _string_field(params: Mapping[str, JSONValue], key: str) -> str:
    value = params.get(key)
    if isinstance(value, str):
        return value
    raise ServerNotificationDecodeError(f"notification field {key} must be a string")


def _object_field(params: Mapping[str, JSONValue], key: str) -> dict[str, JSONValue]:
    value = params.get(key)
    if isinstance(value, Mapping):
        return dict(value)
    raise ServerNotificationDecodeError(f"notification field {key} must be an object")


def _int_field(params: Mapping[str, JSONValue], key: str) -> int:
    value = params.get(key)
    if isinstance(value, bool):
        raise ServerNotificationDecodeError(f"notification field {key} must be an integer")
    if isinstance(value, int):
        return value
    raise ServerNotificationDecodeError(f"notification field {key} must be an integer")
