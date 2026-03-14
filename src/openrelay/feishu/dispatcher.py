from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Awaitable, Callable

import lark_oapi as lark
from lark_oapi.core.enum import LogLevel
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTrigger, P2CardActionTriggerResponse
from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1

from openrelay.core import AppConfig, IncomingMessage

from .common import LOGGER
from .messenger import FeishuMessenger
from .parsing import parse_card_action_event, parse_message_event


class FeishuEventDispatcher:
    def __init__(
        self,
        config: AppConfig,
        loop: asyncio.AbstractEventLoop,
        dispatch_message: Callable[[IncomingMessage], Awaitable[None]],
        messenger: FeishuMessenger | None = None,
        log: logging.Logger | None = None,
    ):
        self.config = config
        self.loop = loop
        self.dispatch_message = dispatch_message
        self.messenger = messenger
        self.logger = log or LOGGER

    def build(self) -> lark.EventDispatcherHandler:
        builder = lark.EventDispatcherHandler.builder(self.config.feishu.encrypt_key, self.config.feishu.verify_token, LogLevel.INFO)
        builder.register_p2_im_message_receive_v1(self._handle_message_event)
        builder.register_p2_card_action_trigger(self._handle_card_action)
        return builder.build()

    async def _dispatch_with_media_resolution(self, message: IncomingMessage) -> None:
        if self.messenger is not None and message.remote_image_keys:
            local_image_paths: list[str] = []
            for image_key in message.remote_image_keys:
                try:
                    image_path = await self.messenger.download_message_resource_to_file(message.message_id, image_key, resource_type="image")
                except Exception:
                    self.logger.exception(
                        "failed to download inbound Feishu image message_id=%s image_key=%s",
                        message.message_id,
                        image_key,
                    )
                    continue
                local_image_paths.append(image_path)
            if local_image_paths:
                message = replace(message, remote_image_keys=(), local_image_paths=tuple(local_image_paths))
        await self.dispatch_message(message)

    def _schedule(self, message: IncomingMessage) -> None:
        self.loop.call_soon_threadsafe(lambda: asyncio.create_task(self._dispatch_with_media_resolution(message)))

    def _handle_message_event(self, event: P2ImMessageReceiveV1) -> None:
        parsed = parse_message_event(self.config, event)
        if parsed.type == "message" and parsed.message is not None:
            self._schedule(parsed.message)

    def _handle_card_action(self, event: P2CardActionTrigger) -> P2CardActionTriggerResponse:
        parsed = parse_card_action_event(event)
        if parsed.type == "message" and parsed.message is not None:
            self._schedule(parsed.message)
        return P2CardActionTriggerResponse()
