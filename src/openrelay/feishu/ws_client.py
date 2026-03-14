from __future__ import annotations

import asyncio
import importlib
import logging
import threading
from typing import Any

import lark_oapi as lark

from openrelay.core import AppConfig


LOGGER = logging.getLogger("openrelay.feishu.ws")


class FeishuWebSocketClient:
    def __init__(
        self,
        config: AppConfig,
        event_handler: lark.EventDispatcherHandler,
        log: logging.Logger | None = None,
    ):
        self.config = config
        self.event_handler = event_handler
        self.logger = log or LOGGER
        self._thread: threading.Thread | None = None
        self._client: Any = None
        self._ws_module: Any = None
        self._start_error: BaseException | None = None

    @property
    def connected(self) -> bool:
        return bool(self._client is not None and getattr(self._client, "_conn", None) is not None)

    async def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._start_error = None
        started = threading.Event()

        def run() -> None:
            try:
                ws_module = importlib.import_module("lark_oapi.ws.client")
                ws_client_cls = getattr(ws_module, "Client")
                self._ws_module = ws_module
                self._client = ws_client_cls(
                    self.config.feishu.app_id,
                    self.config.feishu.app_secret,
                    event_handler=self.event_handler,
                    log_level=lark.LogLevel.INFO,
                    auto_reconnect=True,
                )
                started.set()
                self._client.start()
            except BaseException as exc:
                self._start_error = exc
                self.logger.exception("official feishu websocket client exited")
                started.set()
            finally:
                self._client = None

        self._thread = threading.Thread(target=run, name="openrelay-feishu-ws", daemon=True)
        self._thread.start()
        await asyncio.to_thread(started.wait, 10)
        if self._start_error is not None:
            raise RuntimeError(f"failed to start official Feishu websocket client: {self._start_error}")

    async def close(self) -> None:
        client = self._client
        ws_module = self._ws_module
        if client is None or ws_module is None:
            return
        client._auto_reconnect = False
        loop = getattr(ws_module, "loop", None)
        if loop is not None:
            future = asyncio.run_coroutine_threadsafe(client._disconnect(), loop)
            try:
                await asyncio.wrap_future(future)
            except Exception:
                pass

            def stop_loop() -> None:
                for task in list(asyncio.all_tasks(loop)):
                    task.cancel()
                loop.stop()

            try:
                loop.call_soon_threadsafe(stop_loop)
            except Exception:
                pass
        if self._thread is not None:
            await asyncio.to_thread(self._thread.join, 1)
            self._thread = None
