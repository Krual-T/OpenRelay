from __future__ import annotations

import pytest

from openrelay.backends.codex_adapter_v2.jsonrpc import JSONRPCRequest, JSONRPCResponse
from openrelay.backends.codex_adapter_v2.requests import (
    SERVER_REQUEST_VARIANTS,
    ServerRequest,
    ServerRequestDecodeError,
    ServerRequestPayload,
    ServerResponse,
    parse_server_request,
)


def test_server_request_methods_match_official_protocol() -> None:
    assert SERVER_REQUEST_VARIANTS == {
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


def test_parse_server_request_keeps_request_id_method_and_full_params() -> None:
    params = {
        "threadId": "thread_1",
        "turnId": "turn_1",
        "itemId": "item_1",
        "command": "pytest",
        "cwd": "/repo",
    }

    request = parse_server_request(
        JSONRPCRequest(
            id="approval_1",
            method="item/commandExecution/requestApproval",
            params=params,
        )
    )

    assert request == ServerRequest(
        variant="CommandExecutionRequestApproval",
        method="item/commandExecution/requestApproval",
        request_id="approval_1",
        params=params,
    )
    assert request.id() == "approval_1"
    assert request.to_jsonrpc_payload() == {
        "id": "approval_1",
        "method": "item/commandExecution/requestApproval",
        "params": params,
    }


def test_server_request_payload_builds_request_with_id() -> None:
    payload = ServerRequestPayload(
        variant="DynamicToolCall",
        method="item/tool/call",
        params={"threadId": "thread_1", "toolName": "local_search"},
    )

    assert payload.request_with_id(7) == ServerRequest(
        variant="DynamicToolCall",
        method="item/tool/call",
        request_id=7,
        params={"threadId": "thread_1", "toolName": "local_search"},
    )


def test_server_request_response_from_result_uses_original_request_id() -> None:
    request = ServerRequest(
        variant="ToolRequestUserInput",
        method="item/tool/requestUserInput",
        request_id="input_1",
        params={"threadId": "thread_1"},
    )

    response = request.response_from_result({"input": [{"type": "text", "text": "继续"}]})

    assert response == ServerResponse(
        variant="ToolRequestUserInput",
        method="item/tool/requestUserInput",
        request_id="input_1",
        response={"input": [{"type": "text", "text": "继续"}]},
    )
    assert response.id() == "input_1"
    assert response.to_jsonrpc_response() == JSONRPCResponse(
        id="input_1",
        result={"input": [{"type": "text", "text": "继续"}]},
    )


def test_unknown_server_request_is_rejected() -> None:
    with pytest.raises(ServerRequestDecodeError, match="unsupported server request"):
        parse_server_request(JSONRPCRequest(id=1, method="future/request", params={}))


def test_supported_server_request_requires_object_params() -> None:
    with pytest.raises(ServerRequestDecodeError, match="params must be an object"):
        parse_server_request(JSONRPCRequest(id=1, method="execCommandApproval", params=[]))
