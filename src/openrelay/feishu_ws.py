from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import time
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs, urlparse

from websockets.asyncio.client import connect as ws_connect

from openrelay.config import AppConfig
from openrelay.feishu import FeishuMessenger, parse_webhook_body
from openrelay.feishu_ws_proto import Frame, Header, decode_frame, encode_frame


LOGGER = logging.getLogger("openrelay.feishu_ws")
FRAME_TYPE_CONTROL = 0
FRAME_TYPE_DATA = 1
MESSAGE_TYPE_EVENT = "event"
MESSAGE_TYPE_PING = "ping"
MESSAGE_TYPE_PONG = "pong"
HEADER_TYPE = "type"
HEADER_MESSAGE_ID = "message_id"
HEADER_SUM = "sum"
HEADER_SEQ = "seq"
HEADER_TRACE_ID = "trace_id"
HEADER_BIZ_RT = "biz_rt"
HTTP_OK = 200
HTTP_INTERNAL_SERVER_ERROR = 500
WS_CONFIG_BASE_URL = "https://open.feishu.cn"


@dataclass(slots=True)
class DataCacheItem:
    buffer: list[bytes | None]
    trace_id: str
    message_id: str
    created_time: float


@dataclass(slots=True)
class WSRuntimeConfig:
    connect_url: str = ""
    ping_interval: float = 120.0
    reconnect_count: int = -1
    reconnect_interval: float = 120.0
    reconnect_nonce: float = 30.0
    device_id: str = ""
    service_id: str = "0"
    auto_reconnect: bool = True


class DataCache:
    def __init__(self, logger: logging.Logger):
        self.cache: dict[str, DataCacheItem] = {}
        self.logger = logger

    def merge_data(self, *, message_id: str, total: int, seq: int, trace_id: str, data: bytes) -> dict[str, Any] | None:
        self._clear_expired()
        cached = self.cache.get(message_id)
        if cached is None:
            buffer: list[bytes | None] = [None] * max(total, 1)
            if 0 <= seq < len(buffer):
                buffer[seq] = data
            self.cache[message_id] = DataCacheItem(buffer=buffer, trace_id=trace_id, message_id=message_id, created_time=time.time())
        else:
            if 0 <= seq < len(cached.buffer):
                cached.buffer[seq] = data
        merged = self.cache.get(message_id)
        if merged is None or any(item is None for item in merged.buffer):
            return None
        merged_bytes = b"".join(item or b"" for item in merged.buffer)
        self.cache.pop(message_id, None)
        return json.loads(merged_bytes.decode("utf-8"))

    def _clear_expired(self) -> None:
        now = time.time()
        for key, value in list(self.cache.items()):
            if now - value.created_time > 10:
                self.logger.debug("dropping expired ws event message_id=%s trace_id=%s", value.message_id, value.trace_id)
                self.cache.pop(key, None)


class FeishuWebSocketClient:
    def __init__(
        self,
        config: AppConfig,
        messenger: FeishuMessenger,
        on_message: Callable[[Any], Awaitable[None]],
        log: logging.Logger | None = None,
    ):
        self.config = config
        self.messenger = messenger
        self.on_message = on_message
        self.logger = log or LOGGER
        self.runtime = WSRuntimeConfig()
        self.data_cache = DataCache(self.logger)
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._ready_event = asyncio.Event()
        self._websocket = None

    @property
    def connected(self) -> bool:
        return self._websocket is not None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        await self._ensure_bot_open_id()
        self._stop_event.clear()
        self._ready_event.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def close(self) -> None:
        self._stop_event.set()
        if self._websocket is not None:
            await self._websocket.close()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _ensure_bot_open_id(self) -> None:
        if self.config.feishu.bot_open_id:
            return
        try:
            self.config.feishu.bot_open_id = await self.messenger.resolve_bot_open_id()
        except Exception as exc:
            self.logger.warning("failed to resolve bot open id for websocket mode: %s", exc)

    async def _run_loop(self) -> None:
        attempts = 0
        while not self._stop_event.is_set():
            try:
                await self._pull_connect_config()
                async with ws_connect(self.runtime.connect_url) as websocket:
                    self._websocket = websocket
                    attempts = 0
                    self._ready_event.set()
                    self.logger.info("feishu websocket connected")
                    ping_task = asyncio.create_task(self._ping_loop(websocket))
                    try:
                        async for raw_message in websocket:
                            if self._stop_event.is_set():
                                break
                            if isinstance(raw_message, str):
                                continue
                            await self._handle_frame(websocket, decode_frame(raw_message))
                    finally:
                        ping_task.cancel()
                        try:
                            await ping_task
                        except asyncio.CancelledError:
                            pass
                        self._websocket = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.exception("feishu websocket loop failed: %s", exc)
            if self._stop_event.is_set() or not self.runtime.auto_reconnect:
                return
            attempts += 1
            if self.runtime.reconnect_count >= 0 and attempts > self.runtime.reconnect_count:
                self.logger.error("feishu websocket exceeded reconnect count")
                return
            await asyncio.sleep(max(self.runtime.reconnect_nonce, self.runtime.reconnect_interval))

    async def _pull_connect_config(self) -> None:
        response = await self.messenger._client.post(
            f"{WS_CONFIG_BASE_URL}/callback/ws/endpoint",
            json={"AppID": self.config.feishu.app_id, "AppSecret": self.config.feishu.app_secret},
            headers={"locale": "zh"},
            timeout=15.0,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"pull ws config failed: {payload}")
        url = str(payload.get("data", {}).get("URL") or "")
        if not url:
            raise RuntimeError(f"pull ws config returned no URL: {payload}")
        client_config = payload.get("data", {}).get("ClientConfig") if isinstance(payload.get("data", {}).get("ClientConfig"), dict) else {}
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        self.runtime.connect_url = url
        self.runtime.device_id = (query.get("device_id") or [""])[0]
        self.runtime.service_id = (query.get("service_id") or ["0"])[0]
        self.runtime.ping_interval = float(client_config.get("PingInterval", 120))
        self.runtime.reconnect_count = int(client_config.get("ReconnectCount", -1))
        self.runtime.reconnect_interval = float(client_config.get("ReconnectInterval", 120))
        self.runtime.reconnect_nonce = float(client_config.get("ReconnectNonce", 30))

    async def _ping_loop(self, websocket) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(max(self.runtime.ping_interval, 1))
            if self._stop_event.is_set():
                return
            frame = Frame(
                seq_id=0,
                log_id=0,
                service=int(self.runtime.service_id or 0),
                method=FRAME_TYPE_CONTROL,
                headers=[Header(key=HEADER_TYPE, value=MESSAGE_TYPE_PING)],
            )
            await websocket.send(encode_frame(frame))

    async def _handle_frame(self, websocket, frame: Frame) -> None:
        if frame.method == FRAME_TYPE_CONTROL:
            await self._handle_control_frame(frame)
            return
        if frame.method == FRAME_TYPE_DATA:
            await self._handle_event_frame(websocket, frame)

    async def _handle_control_frame(self, frame: Frame) -> None:
        headers = {header.key: header.value for header in frame.headers}
        msg_type = headers.get(HEADER_TYPE, "")
        if msg_type == MESSAGE_TYPE_PONG and frame.payload:
            payload = json.loads(frame.payload.decode("utf-8"))
            self.runtime.ping_interval = float(payload.get("PingInterval", self.runtime.ping_interval))
            self.runtime.reconnect_count = int(payload.get("ReconnectCount", self.runtime.reconnect_count))
            self.runtime.reconnect_interval = float(payload.get("ReconnectInterval", self.runtime.reconnect_interval))
            self.runtime.reconnect_nonce = float(payload.get("ReconnectNonce", self.runtime.reconnect_nonce))

    async def _handle_event_frame(self, websocket, frame: Frame) -> None:
        headers = {header.key: header.value for header in frame.headers}
        if headers.get(HEADER_TYPE) != MESSAGE_TYPE_EVENT:
            return
        message_id = headers.get(HEADER_MESSAGE_ID, "")
        total = int(headers.get(HEADER_SUM, "1") or "1")
        seq = int(headers.get(HEADER_SEQ, "0") or "0")
        trace_id = headers.get(HEADER_TRACE_ID, "")
        merged = self.data_cache.merge_data(message_id=message_id, total=total, seq=seq, trace_id=trace_id, data=frame.payload)
        if merged is None:
            return
        response_payload: dict[str, Any] = {"code": HTTP_OK}
        start = time.time()
        try:
            parsed = parse_webhook_body(self.config, merged)
            if parsed.type == "message" and parsed.message is not None:
                await self.on_message(parsed.message)
            elif parsed.type == "challenge":
                response_payload["data"] = parsed.challenge
            elif parsed.type == "reject":
                response_payload["code"] = parsed.status_code
                response_payload["msg"] = json.dumps(parsed.body or {"error": "rejected"}, ensure_ascii=False)
        except Exception as exc:
            response_payload["code"] = HTTP_INTERNAL_SERVER_ERROR
            response_payload["msg"] = str(exc)
            self.logger.exception("failed handling websocket event message_id=%s trace_id=%s", message_id, trace_id)
        elapsed_ms = int((time.time() - start) * 1000)
        ack_headers = list(frame.headers) + [Header(key=HEADER_BIZ_RT, value=str(elapsed_ms))]
        ack = Frame(
            seq_id=frame.seq_id,
            log_id=frame.log_id,
            service=frame.service,
            method=frame.method,
            headers=ack_headers,
            payload=json.dumps(response_payload, ensure_ascii=False).encode("utf-8"),
        )
        await websocket.send(encode_frame(ack))
