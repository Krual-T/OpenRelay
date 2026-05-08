from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

from .jsonrpc import JSONRPCRequest, JSONRPCResponse, RequestId

JSONValue: TypeAlias = Any


class ServerRequestDecodeError(ValueError):
    """Raised when an app-server request does not match a supported server request."""


SERVER_REQUEST_VARIANTS: dict[str, str] = {
    "item/commandExecution/requestApproval": "CommandExecutionRequestApproval",
    "item/fileChange/requestApproval": "FileChangeRequestApproval",
    "item/tool/requestUserInput": "ToolRequestUserInput",
    "mcpServer/elicitation/request": "McpServerElicitationRequest",
    "item/permissions/requestApproval": "PermissionsRequestApproval",
    "item/tool/call": "DynamicToolCall",
    "account/chatgptAuthTokens/refresh": "ChatgptAuthTokensRefresh",
    "applyPatchApproval": "ApplyPatchApproval",
    "execCommandApproval": "ExecCommandApproval",
}

_SERVER_REQUEST_METHODS: dict[str, str] = {
    variant: method for method, variant in SERVER_REQUEST_VARIANTS.items()
}


@dataclass(frozen=True, slots=True)
class ServerRequest:
    variant: str
    method: str
    request_id: RequestId
    params: dict[str, JSONValue]

    def id(self) -> RequestId:
        return self.request_id

    def response_from_result(self, result: JSONValue) -> ServerResponse:
        return ServerResponse(
            variant=self.variant,
            method=self.method,
            request_id=self.request_id,
            response=result,
        )

    def to_jsonrpc_payload(self) -> dict[str, JSONValue]:
        return {
            "id": self.request_id,
            "method": self.method,
            "params": self.params,
        }


@dataclass(frozen=True, slots=True)
class ServerResponse:
    variant: str
    method: str
    request_id: RequestId
    response: JSONValue

    def id(self) -> RequestId:
        return self.request_id

    def to_jsonrpc_response(self) -> JSONRPCResponse:
        return JSONRPCResponse(id=self.request_id, result=self.response)

    def to_protocol_payload(self) -> dict[str, JSONValue]:
        return {
            "id": self.request_id,
            "method": self.method,
            "response": self.response,
        }


@dataclass(frozen=True, slots=True)
class ServerRequestPayload:
    variant: str
    method: str
    params: dict[str, JSONValue]

    def request_with_id(self, request_id: RequestId) -> ServerRequest:
        return ServerRequest(
            variant=self.variant,
            method=self.method,
            request_id=request_id,
            params=self.params,
        )

    @classmethod
    def from_variant(
        cls,
        variant: str,
        params: Mapping[str, JSONValue] | None = None,
    ) -> ServerRequestPayload:
        method = _SERVER_REQUEST_METHODS.get(variant)
        if method is None:
            raise ServerRequestDecodeError(f"unsupported server request payload variant `{variant}`")
        return cls(variant=variant, method=method, params=dict(params or {}))


def parse_server_request(message: JSONRPCRequest) -> ServerRequest:
    if not isinstance(message, JSONRPCRequest):
        raise TypeError(f"expected JSONRPCRequest, got {type(message).__name__}")
    variant = SERVER_REQUEST_VARIANTS.get(message.method)
    if variant is None:
        raise ServerRequestDecodeError(f"unsupported server request `{message.method}`")
    return ServerRequest(
        variant=variant,
        method=message.method,
        request_id=message.id,
        params=dict(_coerce_params(message.params)),
    )


def _coerce_params(value: JSONValue | None) -> Mapping[str, JSONValue]:
    if isinstance(value, Mapping):
        return value
    if value is None:
        return {}
    raise ServerRequestDecodeError(
        f"server request params must be an object, got {type(value).__name__}"
    )
