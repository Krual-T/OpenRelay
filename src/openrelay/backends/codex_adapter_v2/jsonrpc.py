from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, TypeAlias

RequestId: TypeAlias = int | str
JSONValue: TypeAlias = Any


class JSONRPCDecodeError(ValueError):
    """Raised when an app-server payload does not match a supported JSON-RPC shape."""


@dataclass(frozen=True, slots=True)
class JSONRPCRequest:
    id: RequestId
    method: str
    params: JSONValue | None = None
    trace: JSONValue | None = None


@dataclass(frozen=True, slots=True)
class JSONRPCNotification:
    method: str
    params: JSONValue | None = None


@dataclass(frozen=True, slots=True)
class JSONRPCResponse:
    id: RequestId
    result: JSONValue


@dataclass(frozen=True, slots=True)
class JSONRPCErrorError:
    code: int
    message: str
    data: JSONValue | None = None


@dataclass(frozen=True, slots=True)
class JSONRPCError:
    id: RequestId
    error: JSONRPCErrorError


JSONRPCMessage: TypeAlias = JSONRPCRequest | JSONRPCNotification | JSONRPCResponse | JSONRPCError


def parse_jsonrpc_message(raw: str | bytes | bytearray | Mapping[str, Any]) -> JSONRPCMessage:
    payload = _load_payload(raw)
    if "id" in payload and "method" in payload:
        return JSONRPCRequest(
            id=_coerce_request_id(payload["id"]),
            method=_coerce_method(payload["method"]),
            params=payload.get("params"),
            trace=payload.get("trace"),
        )
    if "method" in payload:
        return JSONRPCNotification(
            method=_coerce_method(payload["method"]),
            params=payload.get("params"),
        )
    if "id" in payload and "result" in payload:
        return JSONRPCResponse(
            id=_coerce_request_id(payload["id"]),
            result=payload.get("result"),
        )
    if "id" in payload and "error" in payload:
        return JSONRPCError(
            id=_coerce_request_id(payload["id"]),
            error=_coerce_error(payload["error"]),
        )
    raise JSONRPCDecodeError("unsupported JSON-RPC message shape")


def to_jsonrpc_payload(message: JSONRPCMessage) -> dict[str, Any]:
    if isinstance(message, JSONRPCRequest):
        payload: dict[str, Any] = {"id": message.id, "method": message.method}
        if message.params is not None:
            payload["params"] = message.params
        if message.trace is not None:
            payload["trace"] = message.trace
        return payload
    if isinstance(message, JSONRPCNotification):
        payload = {"method": message.method}
        if message.params is not None:
            payload["params"] = message.params
        return payload
    if isinstance(message, JSONRPCResponse):
        return {"id": message.id, "result": message.result}
    if isinstance(message, JSONRPCError):
        error: dict[str, Any] = {"code": message.error.code, "message": message.error.message}
        if message.error.data is not None:
            error["data"] = message.error.data
        return {"id": message.id, "error": error}
    raise TypeError(f"unsupported JSON-RPC message: {message!r}")


def serialize_jsonrpc_message(message: JSONRPCMessage) -> str:
    return json.dumps(to_jsonrpc_payload(message), ensure_ascii=False, separators=(",", ":"))


def _load_payload(raw: str | bytes | bytearray | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        payload: Any = dict(raw)
    else:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise JSONRPCDecodeError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise JSONRPCDecodeError("JSON-RPC message must be an object")
    return payload


def _coerce_request_id(value: Any) -> RequestId:
    if isinstance(value, bool):
        raise JSONRPCDecodeError(f"unsupported JSON-RPC request id: {value!r}")
    if isinstance(value, (int, str)):
        return value
    raise JSONRPCDecodeError(f"unsupported JSON-RPC request id: {value!r}")


def _coerce_method(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise JSONRPCDecodeError(f"unsupported JSON-RPC method: {value!r}")
    return value


def _coerce_error(value: Any) -> JSONRPCErrorError:
    if not isinstance(value, Mapping):
        raise JSONRPCDecodeError("JSON-RPC error must be an object")
    code = value.get("code")
    if isinstance(code, bool) or not isinstance(code, int):
        raise JSONRPCDecodeError(f"unsupported JSON-RPC error.code: {code!r}")
    message = value.get("message")
    if not isinstance(message, str):
        raise JSONRPCDecodeError(f"unsupported JSON-RPC error.message: {message!r}")
    return JSONRPCErrorError(code=code, message=message, data=value.get("data"))
