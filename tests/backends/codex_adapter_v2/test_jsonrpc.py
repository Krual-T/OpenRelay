from __future__ import annotations

import pytest

from openrelay.backends.codex_adapter_v2.jsonrpc import (
    JSONRPCDecodeError,
    JSONRPCError,
    JSONRPCErrorError,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
    parse_jsonrpc_message,
    serialize_jsonrpc_message,
    to_jsonrpc_payload,
)


def test_parse_notification_text_into_jsonrpc_notification() -> None:
    message = parse_jsonrpc_message(
        '{"method":"item/agentMessage/delta","params":{"threadId":"thread_1","turnId":"turn_1","itemId":"item_1","delta":"你好"}}'
    )

    assert message == JSONRPCNotification(
        method="item/agentMessage/delta",
        params={
            "threadId": "thread_1",
            "turnId": "turn_1",
            "itemId": "item_1",
            "delta": "你好",
        },
    )


def test_parse_request_response_and_error_shapes() -> None:
    assert parse_jsonrpc_message({"id": 1, "method": "thread/list", "params": {"limit": 20}}) == JSONRPCRequest(
        id=1,
        method="thread/list",
        params={"limit": 20},
    )
    assert parse_jsonrpc_message({"id": "initialize", "result": {}}) == JSONRPCResponse(
        id="initialize",
        result={},
    )
    assert parse_jsonrpc_message(
        {"id": 2, "error": {"code": -32601, "message": "unsupported", "data": {"method": "x"}}}
    ) == JSONRPCError(
        id=2,
        error=JSONRPCErrorError(code=-32601, message="unsupported", data={"method": "x"}),
    )


def test_serialize_message_omits_absent_optional_fields() -> None:
    message = JSONRPCRequest(id=1, method="initialize")

    assert to_jsonrpc_payload(message) == {"id": 1, "method": "initialize"}
    assert serialize_jsonrpc_message(message) == '{"id":1,"method":"initialize"}'


def test_parse_rejects_invalid_jsonrpc_shapes() -> None:
    with pytest.raises(JSONRPCDecodeError, match="object"):
        parse_jsonrpc_message("[]")

    with pytest.raises(JSONRPCDecodeError, match="request id"):
        parse_jsonrpc_message({"id": None, "result": {}})

    with pytest.raises(JSONRPCDecodeError, match="method"):
        parse_jsonrpc_message({"method": 3, "params": {}})

    with pytest.raises(JSONRPCDecodeError, match="error.code"):
        parse_jsonrpc_message({"id": 1, "error": {"code": "bad", "message": "broken"}})
