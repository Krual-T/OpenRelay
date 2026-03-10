from __future__ import annotations

import asyncio
from collections import defaultdict, deque
import logging
import os
from pathlib import Path
import sys
from typing import Any, Awaitable, Callable

from openrelay.backends import Backend, BackendDescriptor, BackendContext, CodexBackend, build_builtin_backend_descriptors, instantiate_builtin_backends
from openrelay.config import AppConfig
from openrelay.feishu import FeishuMessenger
from openrelay.follow_up import QueuedFollowUp
from openrelay.help_renderer import HelpRenderer
from openrelay.models import ActiveRun, IncomingMessage, SessionRecord, utc_now
from openrelay.panel_card import build_panel_card
from openrelay.render import render_live_status_markdown
from openrelay.streaming_card import FeishuStreamingSession
from openrelay.typing import FeishuTypingManager
from openrelay.release import (
    append_release_event,
    build_release_session_label,
    build_release_switch_note,
    format_release_channel,
    get_release_workspace,
    get_session_workspace_root,
    infer_release_channel,
)
from openrelay.state import StateStore
from openrelay.runtime_live import apply_live_progress, build_reply_card, create_live_reply_state
from openrelay.runtime_commands import PanelCommandArgs, RuntimeCommandHooks, RuntimeCommandRouter
from openrelay.session_browser import SessionBrowser, SessionSortMode
from openrelay.session_list_card import build_session_list_card
from openrelay.session_ux import SessionUX


DEFAULT_SYSTEMD_SERVICE_UNIT = "openrelay.service"
NON_BLOCKING_ACTIVE_RUN_COMMANDS = {"/ping", "/status", "/usage", "/help", "/tools", "/panel", "/restart"}
LOGGER = logging.getLogger("openrelay.runtime")


def get_systemd_service_unit(env: dict[str, str] | None = None) -> str:
    current_env = os.environ if env is None else env
    raw_unit = (current_env.get("OPENRELAY_SYSTEMD_UNIT") or "").strip()
    return raw_unit or DEFAULT_SYSTEMD_SERVICE_UNIT


def is_systemd_service_process(env: dict[str, str] | None = None, pid: int | None = None) -> bool:
    current_env = os.environ if env is None else env
    current_pid = os.getpid() if pid is None else pid
    raw_exec_pid = (current_env.get("SYSTEMD_EXEC_PID") or "").strip()
    if not raw_exec_pid:
        return False
    try:
        return int(raw_exec_pid) == current_pid
    except ValueError:
        return False


class AgentRuntime:
    def __init__(
        self,
        config: AppConfig,
        store: StateStore,
        messenger: FeishuMessenger,
        backends: dict[str, Backend] | None = None,
        backend_descriptors: dict[str, BackendDescriptor] | None = None,
        streaming_session_factory: Callable[[FeishuMessenger], FeishuStreamingSession] | None = None,
        typing_manager: FeishuTypingManager | None = None,
    ):
        self.config = config
        self.store = store
        self.messenger = messenger
        self.backend_descriptors = backend_descriptors or build_builtin_backend_descriptors()
        self.backends = backends or instantiate_builtin_backends(config, self.backend_descriptors)
        if config.backend.default_backend not in self.backends:
            raise ValueError(f"Configured default backend is unavailable: {config.backend.default_backend}")
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._pending_session_inputs: dict[str, deque[IncomingMessage | QueuedFollowUp]] = defaultdict(deque)
        self.active_runs: dict[str, ActiveRun] = {}
        self.streaming_session_factory = streaming_session_factory or (lambda current_messenger: FeishuStreamingSession(current_messenger))
        self.typing_manager = typing_manager or FeishuTypingManager(messenger)
        self.session_browser = SessionBrowser(config, store)
        self.session_ux = SessionUX(config, store)
        self.help_renderer = HelpRenderer(config, store, self.session_ux)
        self.command_router = RuntimeCommandRouter(
            config,
            store,
            self.session_browser,
            self.session_ux,
            self.help_renderer,
            self.backends,
            RuntimeCommandHooks(
                reply=self._reply,
                send_help=self._send_help,
                send_panel=self._send_panel,
                send_session_list=self._send_session_list,
                switch_release_channel=self._switch_release_channel,
                stop=self._handle_stop,
                schedule_restart=self._schedule_restart,
                is_admin=self.is_admin,
                available_backend_names=self.available_backend_names,
            ),
        )
        self._restart_started = False

    async def shutdown(self) -> None:
        await CodexBackend.shutdown_all()
        await self.messenger.close()
        self.store.close()

    def build_session_key(self, message: IncomingMessage) -> str:
        if message.session_key:
            return message.session_key
        parts = [message.chat_type or "unknown", message.chat_id]
        thread_id = message.root_id or message.thread_id
        if thread_id:
            parts.extend(["thread", thread_id])
        if message.chat_type == "group" and self.config.feishu.group_session_scope != "shared":
            parts.extend(["sender", message.session_owner_open_id or message.sender_open_id or "unknown"])
        return ":".join(parts)

    def is_allowed_user(self, sender_open_id: str) -> bool:
        if sender_open_id in self.config.feishu.admin_open_ids:
            return True
        if not self.config.feishu.allowed_open_ids:
            return True
        return sender_open_id in self.config.feishu.allowed_open_ids

    def is_admin(self, sender_open_id: str) -> bool:
        return bool(self.config.feishu.admin_open_ids) and sender_open_id in self.config.feishu.admin_open_ids

    async def dispatch_message(self, message: IncomingMessage) -> None:
        try:
            if not message.text:
                return
            if self.config.feishu.bot_open_id and message.sender_open_id == self.config.feishu.bot_open_id:
                return
            if self.store.remember_message(message.event_id or message.message_id):
                return
            if not message.actionable:
                return
            if not self.is_allowed_user(message.sender_open_id):
                await self._reply(message, "你没有权限使用 openrelay。", command_reply=True)
                return

            session_key = self.build_session_key(message)
            if self._is_stop_command(message.text):
                await self._handle_stop(message, session_key)
                return

            session_lock = self._locks[session_key]
            if session_lock.locked() and self._should_bypass_active_run(message.text):
                session = self.store.load_session(session_key)
                handled = await self._handle_command(message, session_key, session)
                if handled:
                    return
            if session_lock.locked():
                queued_follow_up = self._enqueue_pending_input(session_key, message)
                if queued_follow_up is not None:
                    await self._reply(message, queued_follow_up.acknowledgement_text())
                return

            async with session_lock:
                await self._handle_message_serialized(message, session_key)
        except Exception:
            LOGGER.exception("dispatch_message failed for event_id=%s chat_id=%s", message.event_id, message.chat_id)

    async def _handle_message_serialized(self, message: IncomingMessage, session_key: str) -> None:
        pending_input: IncomingMessage | QueuedFollowUp | None = message
        while pending_input is not None:
            await self._handle_single_serialized_input(pending_input, session_key)
            pending_input = self._dequeue_pending_input(session_key)

    async def _handle_single_serialized_input(self, pending_input: IncomingMessage | QueuedFollowUp, session_key: str) -> None:
        message = pending_input.to_message() if isinstance(pending_input, QueuedFollowUp) else pending_input
        session = self.store.load_session(session_key)
        if message.text.startswith("/"):
            handled = await self._handle_command(message, session_key, session)
            if handled:
                return
        await self._run_backend_turn(message, session_key, session)

    def _enqueue_pending_input(self, session_key: str, message: IncomingMessage) -> QueuedFollowUp | None:
        pending_inputs = self._pending_session_inputs[session_key]
        if self.active_runs.get(session_key) is not None and not message.text.startswith("/"):
            last_input = pending_inputs[-1] if pending_inputs else None
            if isinstance(last_input, QueuedFollowUp):
                last_input.merge(message)
                return last_input
            queued_follow_up = QueuedFollowUp.from_message(message)
            pending_inputs.append(queued_follow_up)
            return queued_follow_up
        pending_inputs.append(message)
        return None

    def _dequeue_pending_input(self, session_key: str) -> IncomingMessage | QueuedFollowUp | None:
        pending_inputs = self._pending_session_inputs.get(session_key)
        if not pending_inputs:
            return None
        next_input = pending_inputs.popleft()
        if not pending_inputs:
            self._pending_session_inputs.pop(session_key, None)
        return next_input

    def _queued_follow_up_count(self, session_key: str) -> int:
        pending_inputs = self._pending_session_inputs.get(session_key)
        if not pending_inputs:
            return 0
        return sum(item.message_count for item in pending_inputs if isinstance(item, QueuedFollowUp))

    async def _run_backend_turn(self, message: IncomingMessage, session_key: str, session: SessionRecord) -> None:
        backend = self.backends.get(session.backend)
        if backend is None:
            await self._reply(message, f"Unsupported backend: {session.backend}")
            return

        cancel_event = asyncio.Event()

        async def cancel(_reason: str) -> None:
            cancel_event.set()

        self.active_runs[session_key] = ActiveRun(started_at=utc_now(), description=self.session_ux.shorten(message.text, 72), cancel=cancel)
        typing_state: dict[str, Any] | None = None
        streaming: FeishuStreamingSession | None = None
        streaming_broken = False
        last_live_text = ""
        spinner_task: asyncio.Task[None] | None = None
        streaming_update_event = asyncio.Event()
        streaming_dirty = False
        live_state = create_live_reply_state(session, self.session_ux.format_cwd)
        if session.backend != "codex":
            live_state["heading"] = "正在生成回复"
            live_state["status"] = "等待流式输出"

        def stop_spinner_task() -> None:
            nonlocal spinner_task
            if spinner_task is None:
                return
            spinner_task.cancel()
            spinner_task = None

        def request_streaming_update() -> None:
            nonlocal streaming_dirty
            if self.config.feishu.stream_mode != "card" or streaming_broken:
                return
            streaming_dirty = True
            streaming_update_event.set()

        async def update_streaming() -> None:
            nonlocal streaming, streaming_broken, last_live_text
            if self.config.feishu.stream_mode != "card" or streaming_broken:
                return
            live_text = render_live_status_markdown(live_state)
            if not live_text or live_text == last_live_text:
                return
            try:
                if streaming is None:
                    streaming = self.streaming_session_factory(self.messenger)
                    await streaming.start(
                        message.chat_id,
                        reply_to_message_id=message.reply_to_message_id or ("" if self._is_card_action_message(message) else message.message_id),
                        root_id=self._root_id_for_message(message),
                    )
                if not streaming.is_active():
                    return
                await streaming.update(live_state)
                last_live_text = live_text
            except Exception:
                has_started = streaming.has_started() if streaming is not None else False
                streaming_broken = True
                if not has_started:
                    streaming = None
                stop_spinner_task()
                LOGGER.exception("streaming update failed for session_key=%s", session_key)

        async def spinner_loop() -> None:
            nonlocal streaming_dirty
            while True:
                try:
                    await asyncio.wait_for(streaming_update_event.wait(), timeout=1.0)
                    streaming_update_event.clear()
                except asyncio.TimeoutError:
                    live_state["spinner_frame"] = (int(live_state.get("spinner_frame", 0) or 0) + 1) % 3
                    streaming_dirty = True
                if not streaming_dirty:
                    continue
                streaming_dirty = False
                try:
                    await update_streaming()
                except Exception:
                    stop_spinner_task()
                    LOGGER.exception("streaming tick failed for session_key=%s", session_key)
                    return

        try:
            session = self.session_ux.label_session_if_needed(session, message.text)
            self.store.save_session(session)
            self.store.append_message(session.session_id, "user", message.text)

            if message.message_id and self.config.feishu.stream_mode != "off":
                try:
                    typing_state = await self.typing_manager.add(message.message_id)
                except Exception:
                    LOGGER.exception("typing start failed for message_id=%s", message.message_id)

            if self.config.feishu.stream_mode == "card":
                await update_streaming()
                spinner_task = asyncio.create_task(spinner_loop())

            async def on_partial_text(partial_text: str) -> None:
                if not partial_text.strip():
                    return
                live_state["heading"] = "正在生成回复"
                live_state["status"] = "正在输出内容"
                live_state["partial_text"] = partial_text
                request_streaming_update()

            async def on_progress(event: dict[str, Any]) -> None:
                apply_live_progress(live_state, event)
                request_streaming_update()

            reply = await backend.run(
                session,
                message.text,
                BackendContext(
                    workspace_root=get_session_workspace_root(self.config, session),
                    cancel_event=cancel_event,
                    on_partial_text=on_partial_text,
                    on_progress=on_progress,
                ),
            )
            updated = SessionRecord(
                session_id=session.session_id,
                base_key=session.base_key,
                backend=session.backend,
                cwd=session.cwd,
                label=session.label,
                model_override=session.model_override,
                safety_mode=session.safety_mode,
                native_session_id=reply.native_session_id or session.native_session_id,
                release_channel=session.release_channel,
                last_usage=reply.metadata.get("usage", {}) if isinstance(reply.metadata, dict) else {},
                created_at=session.created_at,
            )
            updated = self.store.save_session(updated)
            self.store.append_message(updated.session_id, "assistant", reply.text)
            stop_spinner_task()
            await self._reply_final(message, reply.text or "(empty reply)", streaming)
        except Exception as exc:
            stop_spinner_task()
            if "interrupted by /stop" in str(exc).lower() or "interrupted" in str(exc).lower():
                if streaming is not None and streaming.has_started():
                    try:
                        await streaming.close("已停止当前回复。")
                    except Exception:
                        LOGGER.exception("streaming close failed after interrupt")
                else:
                    await self._reply_final(message, "已停止当前回复。", None)
            else:
                await self._reply_final(message, f"处理失败：{exc}", streaming)
        finally:
            stop_spinner_task()
            self.active_runs.pop(session_key, None)
            if typing_state is not None:
                try:
                    await self.typing_manager.remove(typing_state)
                except Exception:
                    LOGGER.exception("typing stop failed for message_id=%s", message.message_id)

    async def _handle_command(self, message: IncomingMessage, session_key: str, session: SessionRecord) -> bool:
        return await self.command_router.handle(message, session_key, session)

    async def _handle_stop(self, message: IncomingMessage, session_key: str) -> None:
        active = self.active_runs.get(session_key)
        if active is None:
            await self._reply(message, "当前没有进行中的回复。", command_reply=True)
            return
        await active.cancel("interrupted by /stop")
        queued_follow_up_count = self._queued_follow_up_count(session_key)
        stop_message = "已发送停止请求，正在中断当前回复。"
        if queued_follow_up_count > 0:
            stop_message = f"{stop_message[:-1]} 停止后会继续处理已收到的 {queued_follow_up_count} 条补充消息。"
        await self._reply(message, stop_message, command_reply=True)

    async def _switch_release_channel(
        self,
        message: IncomingMessage,
        session_key: str,
        session: SessionRecord,
        target_channel: str,
        command_name: str,
        reason: str = "",
    ) -> None:
        workspace_dir = get_release_workspace(self.config, target_channel)
        if not workspace_dir.exists():
            await self._reply(message, f"{target_channel} 工作目录不存在：{workspace_dir}", command_reply=True)
            return
        active = self.active_runs.get(session_key)
        cancelled_active_run = active is not None
        if active is not None:
            await active.cancel(f"interrupted by {command_name}")
        next_session = self.store.create_next_session(session_key, session, build_release_session_label(target_channel))
        next_session.release_channel = target_channel
        next_session.cwd = str(workspace_dir)
        next_session.native_session_id = ""
        if target_channel == "main":
            next_session.safety_mode = "read-only"
        self.store.save_session(next_session)
        event = append_release_event(
            self.config,
            {
                "type": "release.force-stable" if target_channel == "main" else "release.switch",
                "command": command_name,
                "reason": reason,
                "session_key": session_key,
                "chat_id": message.chat_id,
                "operator_open_id": message.sender_open_id,
                "from_channel": infer_release_channel(self.config, session),
                "to_channel": target_channel,
                "previous_session_id": session.session_id,
                "next_session_id": next_session.session_id,
                "previous_cwd": session.cwd,
                "next_cwd": next_session.cwd,
                "previous_model": self.session_ux.effective_model(session),
                "next_model": self.session_ux.effective_model(next_session),
                "previous_sandbox": session.safety_mode,
                "next_sandbox": next_session.safety_mode,
                "cancelled_active_run": cancelled_active_run,
            },
        )
        self.store.append_message(next_session.session_id, "assistant", build_release_switch_note(event))
        await self._reply(
            message,
            "\n".join(
                filter(
                    None,
                    [
                        "已强制切到 main 稳定版本。" if target_channel == "main" else "已切到 develop 修复版本。",
                        f"session_id={next_session.session_id}",
                        f"channel={format_release_channel(target_channel)}",
                        f"cwd={self.session_ux.format_cwd(next_session.cwd, next_session)}",
                        f"sandbox={next_session.safety_mode}",
                        f"reason={reason}" if reason else "",
                        "已中断上一条进行中的回复。" if cancelled_active_run else "",
                        "已写入切换记录，后续智能体可据此继续修复。",
                    ],
                )
            ),
            command_reply=True,
        )

    def _build_card_action_context(self, message: IncomingMessage, session_key: str) -> dict[str, str]:
        return {
            "rootId": message.root_id,
            "threadId": message.thread_id or message.root_id,
            "sessionKey": session_key,
            "sessionOwnerOpenId": message.session_owner_open_id or (message.sender_open_id if message.chat_type == "group" and self.config.feishu.group_session_scope != "shared" else ""),
        }

    async def _send_help(self, message: IncomingMessage, session_key: str, session: SessionRecord) -> None:
        card = self.help_renderer.build_card(session, self.available_backend_names(), self._build_card_action_context(message, session_key))
        try:
            await self.messenger.send_interactive_card(
                message.chat_id,
                card,
                reply_to_message_id=self._command_reply_target(message),
                root_id=self._root_id_for_message(message),
                force_new_message=self._should_force_new_message_for_command_card(message),
                update_message_id=self._command_card_update_target(message),
            )
        except Exception:
            await self._reply(message, self.help_renderer.build_text(session, self.available_backend_names()), command_reply=True, command_name="/help")

    async def _send_panel(self, message: IncomingMessage, session_key: str, session: SessionRecord, args: PanelCommandArgs) -> None:
        panel_info = self._build_panel_base_info(message, session_key, session, args.view)
        fallback_text = ""
        if args.view == "sessions":
            session_page = self.session_browser.list_page(session_key, session, page=args.page, sort_mode=args.sort_mode)
            card = build_panel_card(
                {
                    **panel_info,
                    "page": session_page.page,
                    "total_pages": session_page.total_pages,
                    "sort_mode": session_page.sort_mode,
                    "sessions": self.session_ux.build_session_display_entries(session_page.entries, start_index=session_page.start_index),
                }
            )
            fallback_text = self._build_panel_sessions_text(session_page)
        elif args.view == "directories":
            directory_shortcuts = self.session_ux.build_directory_shortcut_entries(session)
            card = build_panel_card({**panel_info, "directory_shortcuts": directory_shortcuts})
            fallback_text = self._build_panel_directories_text(directory_shortcuts)
        elif args.view == "commands":
            command_entries = self._build_panel_command_entries()
            card = build_panel_card({**panel_info, "command_entries": command_entries})
            fallback_text = self._build_panel_commands_text(command_entries)
        elif args.view == "status":
            status_entries = self._build_panel_status_entries(session)
            card = build_panel_card({**panel_info, "status_entries": status_entries})
            fallback_text = self._build_panel_status_text(status_entries)
        else:
            entries = self.session_browser.list_entries(session_key, session, limit=6)
            directory_shortcuts = self.session_ux.build_directory_shortcut_entries(session)
            card = build_panel_card(
                {
                    **panel_info,
                    "sessions": self.session_ux.build_session_display_entries(entries),
                    "directory_shortcuts": directory_shortcuts,
                }
            )
            fallback_text = self._build_panel_home_text(session, entries, directory_shortcuts)
        try:
            await self.messenger.send_interactive_card(
                message.chat_id,
                card,
                reply_to_message_id=self._command_reply_target(message),
                root_id=self._root_id_for_message(message),
                force_new_message=self._should_force_new_message_for_command_card(message),
                update_message_id=self._command_card_update_target(message),
            )
        except Exception:
            await self._reply(message, fallback_text, command_reply=True, command_name="/panel")

    async def _send_session_list(self, message: IncomingMessage, session_key: str, session: SessionRecord, page: int, sort_mode: SessionSortMode) -> None:
        session_page = self.session_browser.list_page(session_key, session, page=page, sort_mode=sort_mode)
        card = build_session_list_card(
            {
                "session_id": session.session_id,
                "current_title": self.session_ux.build_session_title(session.label, session.session_id),
                "channel": format_release_channel(infer_release_channel(self.config, session)),
                "cwd": self.session_ux.format_cwd(session.cwd, session),
                "page": session_page.page,
                "total_pages": session_page.total_pages,
                "total_entries": session_page.total_entries,
                "sort_mode": session_page.sort_mode,
                "has_previous": session_page.has_previous,
                "has_next": session_page.has_next,
                "action_context": self._build_card_action_context(message, session_key),
                "sessions": self.session_ux.build_session_display_entries(session_page.entries, start_index=session_page.start_index),
            }
        )
        try:
            await self.messenger.send_interactive_card(
                message.chat_id,
                card,
                reply_to_message_id=self._command_reply_target(message),
                root_id=self._root_id_for_message(message),
                force_new_message=self._should_force_new_message_for_command_card(message),
                update_message_id=self._command_card_update_target(message),
            )
        except Exception:
            await self._reply(message, self.session_ux.format_session_list_page(session_page), command_reply=True, command_name="/resume")

    def _build_panel_base_info(self, message: IncomingMessage, session_key: str, session: SessionRecord, view: str) -> dict[str, Any]:
        return {
            "view": view,
            "session_id": session.session_id,
            "current_title": self.session_ux.build_session_title(session.label, session.session_id),
            "channel": format_release_channel(infer_release_channel(self.config, session)),
            "cwd": self.session_ux.format_cwd(session.cwd, session),
            "model": self.session_ux.effective_model(session),
            "provider": self.backend_descriptors.get(session.backend).transport if session.backend in self.backend_descriptors else "-",
            "sandbox": session.safety_mode,
            "context_usage": self.session_ux.format_context_usage(session),
            "context_preview": self.session_ux.build_context_preview(session),
            "action_context": self._build_card_action_context(message, session_key),
        }

    def _build_panel_command_entries(self) -> list[dict[str, str]]:
        return [
            {
                "title": "恢复上一条",
                "meta": "会话 · 最短继续路径",
                "preview": "直接回到最近会话，不必先打开列表。",
                "command": "/resume latest",
                "action_label": "恢复上一条",
                "action_type": "primary",
            },
            {
                "title": "浏览会话结果",
                "meta": "会话 · 翻页 / 排序",
                "preview": "在面板里看最近会话，再决定恢复哪一条。",
                "command": "/panel sessions",
                "action_label": "看会话",
            },
            {
                "title": "浏览目录结果",
                "meta": "目录 · 快捷入口",
                "preview": "优先点快捷目录；没有合适入口时再手写 /cwd。",
                "command": "/panel directories",
                "action_label": "看目录",
            },
            {
                "title": "查看完整状态",
                "meta": "状态 · 目录 / 模型 / 上下文",
                "preview": "先确认现场，再决定继续当前任务还是切上下文。",
                "command": "/status",
                "action_label": "看状态",
            },
            {
                "title": "新建隔离会话",
                "meta": "隔离 · 新任务 / 切话题",
                "preview": "当目标已经变了时，不要继续堆在当前会话里。",
                "command": "/new",
                "action_label": "新会话",
            },
            {
                "title": "打开帮助",
                "meta": "引导 · 下一步建议",
                "preview": "需要 prompt 示例或命令速查时使用。",
                "command": "/help",
                "action_label": "打开帮助",
            },
        ]

    def _build_panel_status_entries(self, session: SessionRecord) -> list[dict[str, str]]:
        channel = format_release_channel(infer_release_channel(self.config, session))
        cwd = self.session_ux.format_cwd(session.cwd, session)
        context_preview = self.session_ux.build_context_preview(session) or "还没有可总结的本地上下文。"
        return [
            {
                "title": "当前会话状态",
                "meta": f"{channel} · 目录 {cwd} · sandbox {session.safety_mode}",
                "preview": f"模型 {self.session_ux.effective_model(session)} · 原生会话 {session.native_session_id or 'pending'}",
                "command": "/status",
                "action_label": "完整状态",
                "action_type": "primary",
            },
            {
                "title": "上下文与用量",
                "meta": f"context_usage={self.session_ux.format_context_usage(session)}",
                "preview": context_preview,
                "command": "/usage",
                "action_label": "查看用量",
            },
            {
                "title": "继续当前任务",
                "meta": "如果目标没变，通常直接发消息最快",
                "preview": "要找旧会话就去会话结果；要切目录就去目录结果；不确定下一步时再打开帮助。",
                "command": "/help",
                "action_label": "打开帮助",
            },
        ]

    def _build_panel_home_text(self, session: SessionRecord, entries: list[Any], directory_shortcuts: list[dict[str, str]]) -> str:
        lines = [
            self.session_ux.build_panel_text(session),
            "",
            "结果面：/panel sessions | /panel directories | /panel commands | /panel status",
            "",
            "最近会话：",
            self.session_ux.format_session_list(entries[:3]),
        ]
        if directory_shortcuts:
            lines.extend(["", "目录入口："])
            lines.extend([f"- {entry['label']} -> {entry['display_path']}" for entry in directory_shortcuts[:3]])
        else:
            lines.extend(["", "目录入口：暂无快捷目录；可先 /cwd <path>。"])
        return "\n".join(lines)

    def _build_panel_sessions_text(self, session_page: Any) -> str:
        return "\n".join([
            "OpenRelay 面板 · 会话",
            self.session_ux.format_session_list_page(session_page),
            "",
            "返回总览：/panel。",
        ])

    def _build_panel_directories_text(self, directory_shortcuts: list[dict[str, str]]) -> str:
        lines = [
            "OpenRelay 面板 · 目录",
            "优先点快捷目录；没有合适入口时，再手写 /cwd <path>。",
        ]
        if directory_shortcuts:
            lines.extend([f"- {entry['label']} -> {entry['display_path']}" for entry in directory_shortcuts])
        else:
            lines.append("- 当前没有配置快捷目录。")
        lines.extend(["", "常用动作：/cwd /main /develop"])
        return "\n".join(lines)

    def _build_panel_commands_text(self, command_entries: list[dict[str, str]]) -> str:
        lines = ["OpenRelay 面板 · 命令", "高频动作："]
        lines.extend([f"- {entry['title']}：{entry['preview']} ({entry['command']})" for entry in command_entries])
        return "\n".join(lines)

    def _build_panel_status_text(self, status_entries: list[dict[str, str]]) -> str:
        lines = ["OpenRelay 面板 · 状态", "先看现场，再决定下一步："]
        lines.extend([f"- {entry['title']}：{entry['preview']} ({entry['command']})" for entry in status_entries])
        return "\n".join(lines)

    async def _send_reply_card(
        self,
        message: IncomingMessage,
        text: str,
        title: str = "openrelay 回复",
        *,
        update_message_id: str = "",
    ) -> None:
        await self.messenger.send_interactive_card(
            message.chat_id,
            build_reply_card(text, title),
            reply_to_message_id=message.reply_to_message_id or ("" if self._is_card_action_message(message) else message.message_id),
            root_id=self._root_id_for_message(message),
            update_message_id=update_message_id,
        )

    async def _reply_final(self, message: IncomingMessage, text: str, streaming: FeishuStreamingSession | None) -> None:
        update_message_id = ""
        if streaming is not None and streaming.has_started():
            try:
                update_message_id = streaming.message_id()
                await streaming.close(None)
            except Exception:
                LOGGER.exception("streaming close failed for event_id=%s", message.event_id)
                update_message_id = ""
        if self.config.feishu.stream_mode == "card":
            try:
                await self._send_reply_card(message, text, "openrelay 回复", update_message_id=update_message_id)
                return
            except Exception:
                LOGGER.exception("reply card fallback failed for event_id=%s", message.event_id)
        await self.messenger.send_text(
            message.chat_id,
            text,
            reply_to_message_id=message.reply_to_message_id or ("" if self._is_card_action_message(message) else message.message_id),
            root_id=self._root_id_for_message(message),
        )

    async def _reply(self, message: IncomingMessage, text: str, command_reply: bool = False, command_name: str = "") -> None:
        reply_to = self._command_reply_target(message) if command_reply else (message.reply_to_message_id or ("" if self._is_card_action_message(message) else message.message_id))
        await self.messenger.send_text(
            message.chat_id,
            text,
            reply_to_message_id=reply_to,
            root_id=self._root_id_for_message(message),
            force_new_message=command_reply and self._should_force_new_message_for_command(message, command_name),
        )

    def available_backend_names(self) -> list[str]:
        return sorted(self.backends)

    def _command_reply_target(self, message: IncomingMessage) -> str:
        return message.reply_to_message_id or ("" if self._is_card_action_message(message) else message.message_id)

    def _command_card_update_target(self, message: IncomingMessage) -> str:
        if not self._is_card_action_message(message):
            return ""
        return message.reply_to_message_id

    def _root_id_for_message(self, message: IncomingMessage) -> str:
        return message.root_id or message.thread_id

    def _is_card_action_message(self, message: IncomingMessage) -> bool:
        return message.event_id.startswith("card-action-")

    def _is_top_level_p2p_command(self, message: IncomingMessage) -> bool:
        return message.chat_type == "p2p" and not message.root_id and not message.thread_id

    def _should_force_new_message_for_command(self, message: IncomingMessage, command_name: str) -> bool:
        if not self._is_top_level_p2p_command(message):
            return False
        return command_name not in {"/cwd", "/cd"}

    def _should_force_new_message_for_command_card(self, message: IncomingMessage) -> bool:
        return self._is_top_level_p2p_command(message) and not self._is_card_action_message(message)

    def _is_stop_command(self, text: str) -> bool:
        return text.strip().lower().startswith("/stop")

    def _should_bypass_active_run(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped.startswith("/"):
            return False
        return stripped.split(maxsplit=1)[0].lower() in NON_BLOCKING_ACTIVE_RUN_COMMANDS

    def _schedule_restart(self) -> None:
        if self._restart_started:
            return
        self._restart_started = True
        asyncio.create_task(self._restart_process())

    async def _restart_process(self) -> None:
        await asyncio.sleep(0.4)
        if is_systemd_service_process():
            unit_name = get_systemd_service_unit()
            try:
                await self._restart_systemd_service(unit_name)
                return
            except Exception:
                self._restart_started = False
                LOGGER.exception("failed to restart %s via systemd", unit_name)
                raise
        try:
            await CodexBackend.shutdown_all()
        except Exception:
            LOGGER.exception("failed shutting down backends before restart")
        try:
            os.execvpe(sys.executable, [sys.executable, "-m", "openrelay"], os.environ)
        except Exception:
            self._restart_started = False
            LOGGER.exception("failed to restart openrelay process")
            raise

    async def _restart_systemd_service(self, unit_name: str) -> None:
        process = await asyncio.create_subprocess_exec(
            "systemctl",
            "--user",
            "--no-block",
            "restart",
            unit_name,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=dict(os.environ),
        )
        stderr = b""
        if process.stderr is not None:
            stderr = await process.stderr.read()
        exit_code = await process.wait()
        if exit_code == 0:
            return
        detail = stderr.decode("utf-8", errors="replace").strip()
        message = detail or f"systemctl --user restart exited with code {exit_code}"
        raise RuntimeError(message)
