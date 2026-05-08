"""
CodexV2Session — 一个 Feishu 对话的持久会话。

对应官方 Codex TUI 的 AppServerSession（app_server_session.rs），
管理一个 codex 线程的完整生命周期：
- thread/start → 获得 thread_id
- turn/start → 每轮用户输入
- turn/interrupt → 中断当前轮
- thread/unsubscribe → 关闭线程
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from openrelay.presentation.v2_renderer import TurnV2Renderer

from .client import CodexV2Client, ConnectionClosedError
from .notifications import ServerNotification
from .requests import ServerRequest

LOGGER = logging.getLogger("openrelay.backends.codex_adapter_v2.session")

SPINNER_INTERVAL = 1.0  # spinner 刷新间隔（秒）


class CodexV2Session:
    """一个 Feishu 对话的持久会话。"""

    def __init__(self, client: CodexV2Client) -> None:
        self.client = client
        self.renderer = TurnV2Renderer()
        self.thread_id: str | None = None
        self.cwd: str = ""
        self._active_turn_id: str | None = None
        self._spinner_task: asyncio.Task[None] | None = None

        # 接线：client 收到 notification → renderer 处理
        self.client.on_notification(self._on_notification)
        self.client.on_server_request(self._on_server_request)

    # ---- lifecycle ----

    @classmethod
    async def create(
        cls,
        codex_path: str,
        workspace_root: Path,
        *,
        model: str = "",
        safety_mode: str = "workspace-write",
        sqlite_home: Path | None = None,
        env_extra: dict[str, str] | None = None,
    ) -> CodexV2Session:
        """创建 session 并执行 thread/start 握手。"""
        client = CodexV2Client(
            codex_path=codex_path,
            workspace_root=workspace_root,
            model=model,
            safety_mode=safety_mode,
            sqlite_home=sqlite_home,
            env_extra=env_extra,
        )
        await client.start()

        session = cls(client)
        session.cwd = str(workspace_root)

        # thread/start
        params: dict[str, Any] = {"cwd": session.cwd}
        if model:
            params["model"] = model
        params["sandbox"] = safety_mode
        params["approvalPolicy"] = "never"

        result = await client.request("thread/start", params)
        thread = result.get("thread") if isinstance(result, dict) and isinstance(result.get("thread"), dict) else {}
        session.thread_id = str(thread.get("id") or "")
        if not session.thread_id:
            raise RuntimeError("Codex app-server returned no thread id")

        LOGGER.info("thread started thread_id=%s", session.thread_id)
        return session

    async def shutdown(self) -> None:
        """关闭线程和连接。"""
        self._stop_spinner()
        if self.thread_id is not None:
            try:
                await self.client.notify("thread/unsubscribe", {"threadId": self.thread_id})
            except Exception:
                pass
        await self.client.shutdown()

    # ---- turn ----

    async def run_turn(
        self,
        user_text: str,
        *,
        streaming: Any = None,  # FeishuStreamingSession, 避免硬依赖
        cancel_event: asyncio.Event | None = None,
        model: str | None = None,
    ) -> None:
        """执行完整的一轮 turn：启动 → spinner 循环 → final card。

        streaming 必须有 update_v2(content, card_json) 和 close(final_card) 方法。
        """
        if streaming is not None:
            initial_card = self.renderer.build_initial_card_json()
            await streaming.update_card_json(initial_card)

        await self.start_turn(user_text, model=model)

        if streaming is not None:
            self._spinner_task = asyncio.create_task(
                self._streaming_loop(streaming, cancel_event=cancel_event)
            )

        # 等待 turn 结束（renderer 收到 TurnCompleted/Error 后 agent_turn_running 变 False）
        while self.renderer.state.agent_turn_running:
            if cancel_event is not None and cancel_event.is_set():
                await self.interrupt()
            await asyncio.sleep(0.25)

        self._stop_spinner()

        if streaming is not None:
            final_text = self.renderer.state.assistant_text or ""
            final_card = self.renderer.build_final_card_json(fallback_text=final_text)
            await streaming.close(final_card)

    async def _streaming_loop(
        self,
        streaming: Any,
        *,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """后台 spinner 循环：定期更新 streaming card 内容。"""
        last_content = ""
        while self.renderer.state.agent_turn_running:
            if cancel_event is not None and cancel_event.is_set():
                return
            self.renderer.bump_spinner()
            content = self.renderer.build_streaming_content()
            card_json = self.renderer.build_streaming_card_json()
            if content and content != last_content:
                last_content = content
                try:
                    await streaming.update_v2(content, card_json)
                except Exception:
                    LOGGER.exception("streaming update_v2 failed")
            await asyncio.sleep(SPINNER_INTERVAL)

    def _stop_spinner(self) -> None:
        if self._spinner_task is not None:
            self._spinner_task.cancel()
            self._spinner_task = None

    async def start_turn(self, user_text: str, *, model: str | None = None) -> str:
        """开始新的一轮。返回 turn_id。"""
        if self.thread_id is None:
            raise RuntimeError("session not started")

        params: dict[str, Any] = {
            "threadId": self.thread_id,
            "cwd": self.cwd,
            "approvalPolicy": "never",
            "input": [{"type": "text", "text": user_text}],
        }
        if model:
            params["model"] = model

        result = await self.client.request("turn/start", params)
        turn = result.get("turn") if isinstance(result, dict) and isinstance(result.get("turn"), dict) else {}
        turn_id = str(turn.get("id") or "")

        self._active_turn_id = turn_id
        if turn_id and self.thread_id:
            self.renderer.state.reset_for_new_turn(self.thread_id, turn_id)

        LOGGER.info("turn started thread_id=%s turn_id=%s", self.thread_id, turn_id)
        return turn_id

    async def interrupt(self) -> None:
        """中断当前 turn。"""
        if self.thread_id is None or self._active_turn_id is None:
            return
        await self.client.request(
            "turn/interrupt",
            {"threadId": self.thread_id, "turnId": self._active_turn_id},
        )

    @property
    def is_running(self) -> bool:
        """当前是否在 turn 中。"""
        return self.renderer.state.agent_turn_running

    # ---- internal callbacks ----

    def _on_notification(self, notification: ServerNotification) -> None:
        try:
            self.renderer.handle_server_notification(notification)
        except Exception:
            LOGGER.exception("renderer notification handler failed variant=%s", notification.variant)

    def _on_server_request(self, request: ServerRequest) -> None:
        try:
            self.renderer.handle_server_request(request)
        except Exception:
            LOGGER.exception("renderer server request handler failed variant=%s", request.variant)
