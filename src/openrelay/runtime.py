from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import asdict
import logging
import os
from pathlib import Path
import sys
from typing import Any, Awaitable, Callable

from openrelay.backends import Backend, BackendDescriptor, BackendContext, CodexBackend, build_builtin_backend_descriptors, instantiate_builtin_backends
from openrelay.config import AppConfig, SAFETY_MODES
from openrelay.feishu import FeishuMessenger
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
    read_release_events,
    summarize_release_event,
)
from openrelay.state import StateStore
from openrelay.runtime_live import apply_live_progress, build_reply_card, create_live_reply_state
from openrelay.session_ux import SessionUX


ADMIN_ONLY_COMMANDS = {"/restart"}
DEFAULT_SYSTEMD_SERVICE_UNIT = "openrelay.service"
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
        self.active_runs: dict[str, ActiveRun] = {}
        self.streaming_session_factory = streaming_session_factory or (lambda current_messenger: FeishuStreamingSession(current_messenger))
        self.typing_manager = typing_manager or FeishuTypingManager(messenger)
        self.session_ux = SessionUX(config, store)
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

            async with self._locks[session_key]:
                await self._handle_message_serialized(message, session_key)
        except Exception:
            LOGGER.exception("dispatch_message failed for event_id=%s chat_id=%s", message.event_id, message.chat_id)

    async def _handle_message_serialized(self, message: IncomingMessage, session_key: str) -> None:
        session = self.store.load_session(session_key)
        if message.text.startswith("/"):
            handled = await self._handle_command(message, session_key, session)
            if handled:
                return
        await self._run_backend_turn(message, session_key, session)

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
        raw = message.text.strip()
        parts = raw.split(maxsplit=1)
        name = parts[0].lower()
        arg_text = parts[1].strip() if len(parts) > 1 else ""

        if name in ADMIN_ONLY_COMMANDS and not self.is_admin(message.sender_open_id):
            await self._reply(message, "这个命令只允许管理员使用。", command_reply=True)
            return True

        if name == "/ping":
            await self._reply(message, "pong", command_reply=True)
            return True

        if name in {"/help", "/tools"}:
            await self._reply(message, self._build_help_text(session), command_reply=True)
            return True

        if name == "/panel":
            await self._send_panel(message, session_key, session)
            return True

        if name == "/restart":
            await self._reply(message, "正在重启 openrelay，预计几秒后恢复。", command_reply=True)
            self._schedule_restart()
            return True

        if name in {"/main", "/stable", "/develop"}:
            target_channel = "develop" if name == "/develop" else "main"
            await self._switch_release_channel(message, session_key, session, target_channel, name, arg_text)
            return True

        if name == "/new":
            next_session = self.store.create_next_session(session_key, session, arg_text)
            await self._reply(message, f"已新建会话 {next_session.session_id}{f' ({next_session.label})' if next_session.label else ''}，原生 Codex 会话会在首条真实消息时创建。", command_reply=True)
            return True

        if name == "/clear":
            next_session = self.store.create_next_session(session_key, session, session.label)
            next_session.model_override = session.model_override
            next_session.safety_mode = session.safety_mode
            next_session.release_channel = session.release_channel
            self.store.save_session(next_session)
            await self._reply(message, f"已清空当前上下文，新的会话是 {next_session.session_id}。", command_reply=True)
            return True

        if name == "/model":
            if not arg_text:
                await self._reply(message, f"model={self.session_ux.effective_model(session)}", command_reply=True)
                return True
            next_session = self.store.create_next_session(session_key, session, session.label)
            next_session.model_override = "" if arg_text.lower() in {"default", "reset", "clear"} else arg_text
            self.store.save_session(next_session)
            await self._reply(message, f"model 已切换到 {self.session_ux.effective_model(next_session)}，新的原生会话会在首条真实消息时创建。", command_reply=True)
            return True

        if name in {"/sandbox", "/mode"}:
            if not arg_text:
                await self._reply(message, f"sandbox={session.safety_mode}", command_reply=True)
                return True
            mode = arg_text.lower()
            if mode not in SAFETY_MODES:
                await self._reply(message, "sandbox 仅支持：read-only / workspace-write / danger-full-access", command_reply=True)
                return True
            if mode == "danger-full-access" and not self.is_admin(message.sender_open_id):
                await self._reply(message, "danger-full-access 只允许管理员切换。", command_reply=True)
                return True
            next_session = self.store.create_next_session(session_key, session, session.label)
            next_session.safety_mode = mode
            self.store.save_session(next_session)
            await self._reply(message, f"sandbox 已切换到 {next_session.safety_mode}，新的原生会话会在首条真实消息时创建。", command_reply=True)
            return True

        if name == "/resume":
            merged_sessions = self.session_ux.build_merged_session_list(session_key, session, limit=20)
            if not arg_text or arg_text.lower() == "list":
                await self._reply(
                    message,
                    "\n".join([
                        "最近会话：",
                        self.session_ux.format_merged_session_list(merged_sessions),
                        "",
                        "使用 /resume <序号|session_id|latest> 恢复。想在指定目录进入 Codex：先 /cwd <path>，再发消息。",
                    ]),
                    command_reply=True,
                    command_name=name,
                )
                return True
            resumed = self.session_ux.resume_local_or_native(session_key, session, arg_text, merged_sessions)
            if resumed is None:
                await self._reply(message, f"恢复失败。可用会话：\n{self.session_ux.format_merged_session_list(merged_sessions)}", command_reply=True)
                return True
            await self._reply(message, self.session_ux.format_resume_success(resumed), command_reply=True)
            return True

        if name == "/reset":
            self.store.clear_sessions(session_key)
            self.store.load_session(session_key)
            await self._reply(message, "会话已重置。", command_reply=True)
            return True

        if name in {"/status", "/usage"}:
            latest_release_event = read_release_events(self.config, session_key=session_key, limit=1)
            lines = [
                f"session_base={session_key}",
                f"session_id={session.session_id}",
                f"context_label={session.label or '未命名会话'}",
                f"channel={format_release_channel(infer_release_channel(self.config, session))}",
                f"workspace_root={get_session_workspace_root(self.config, session)}",
                f"model={self.session_ux.effective_model(session)}",
                f"sandbox={session.safety_mode}",
                f"cwd={self.session_ux.format_cwd(session.cwd, session)}",
                f"messages={len(self.store.list_messages(session.session_id))}",
                f"native_session={session.native_session_id or 'pending'}",
                f"release_log={self.config.data_dir / 'release-events.jsonl'}",
                f"server_pid={os.getpid()}",
                f"last_release_event={summarize_release_event(latest_release_event[0]) if latest_release_event else 'none'}",
            ]
            lines.extend(self.session_ux.build_usage_lines(session))
            if name == "/status":
                lines.extend(["", "最近上下文：", *self.session_ux.build_context_lines(session)])
            await self._reply(message, "\n".join(lines), command_reply=True, command_name=name)
            return True

        if name in {"/cwd", "/cd"}:
            if not arg_text:
                await self._reply(
                    message,
                    "\n".join([
                        f"cwd={self.session_ux.format_cwd(session.cwd, session)}",
                        "切换目录：/cwd <path> 或 /cd <path>",
                        "切目录时会创建一个新的空会话；旧会话历史仍可通过 /resume 找回。",
                    ]),
                    command_reply=True,
                    command_name=name,
                )
                return True
            try:
                next_cwd = self.session_ux.resolve_cwd(session.cwd, arg_text, session)
            except ValueError as exc:
                await self._reply(message, f"cwd 切换失败：{exc}", command_reply=True, command_name=name)
                return True
            next_session = self.store.create_next_session(session_key, session, session.label)
            next_session.cwd = str(next_cwd)
            next_session.native_session_id = ""
            self.store.save_session(next_session)
            await self._reply(
                message,
                "\n".join([
                    f"cwd 已切换到 {self.session_ux.format_cwd(next_session.cwd, next_session)}。",
                    "现在直接发消息，就会在这个目录进入 Codex。",
                    "已创建新的空会话；原会话历史还在，想回来可以 /resume list。",
                ]),
                command_reply=True,
                command_name=name,
            )
            return True

        if name == "/backend":
            available = self.available_backend_names()
            if not arg_text or arg_text.lower() == "list":
                await self._reply(message, "\n".join([f"backend={session.backend}", f"available={', '.join(available)}"]), command_reply=True)
                return True
            backend = arg_text.lower()
            if backend not in self.backends:
                await self._reply(message, f"backend 仅支持：{', '.join(available)}", command_reply=True)
                return True
            next_session = self.store.create_next_session(session_key, session, session.label)
            next_session.backend = backend
            next_session.native_session_id = ""
            self.store.save_session(next_session)
            await self._reply(message, f"backend 已切换到 {backend}，新的原生会话将在下一条真实消息时创建。", command_reply=True)
            return True

        if name == "/stop":
            await self._handle_stop(message, session_key)
            return True

        if raw.startswith("/"):
            await self._reply(message, f"本地命令未实现：{name}。发送 /help 查看可用命令。", command_reply=True)
            return True

        return False

    async def _handle_stop(self, message: IncomingMessage, session_key: str) -> None:
        active = self.active_runs.get(session_key)
        if active is None:
            await self._reply(message, "当前没有进行中的回复。", command_reply=True)
            return
        await active.cancel("interrupted by /stop")
        await self._reply(message, "已发送停止请求，正在中断当前回复。", command_reply=True)

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

    async def _send_panel(self, message: IncomingMessage, session_key: str, session: SessionRecord) -> None:
        entries = self.session_ux.build_merged_session_list(session_key, session, limit=6)
        context = {
            "rootId": message.root_id,
            "threadId": message.thread_id or message.root_id,
            "sessionKey": session_key,
            "sessionOwnerOpenId": message.session_owner_open_id or (message.sender_open_id if message.chat_type == "group" and self.config.feishu.group_session_scope != "shared" else ""),
        }
        card = build_panel_card(
            {
                "session_id": session.session_id,
                "current_title": self.session_ux.build_session_title({"label": session.label, "session_id": session.session_id}),
                "channel": format_release_channel(infer_release_channel(self.config, session)),
                "cwd": self.session_ux.format_cwd(session.cwd, session),
                "model": self.session_ux.effective_model(session),
                "provider": self.backend_descriptors.get(session.backend).transport if session.backend in self.backend_descriptors else "-",
                "sandbox": session.safety_mode,
                "context_usage": self.session_ux.format_context_usage(session),
                "context_preview": self.session_ux.build_context_preview(session),
                "action_context": context,
                "sessions": entries,
            }
        )
        try:
            await self.messenger.send_interactive_card(
                message.chat_id,
                card,
                reply_to_message_id=self._command_reply_target(message),
                root_id=self._root_id_for_message(message),
                force_new_message=self._is_top_level_p2p_command(message),
            )
        except Exception:
            await self._reply(message, self.session_ux.build_panel_text(session) + "\n\n" + self.session_ux.format_merged_session_list(entries), command_reply=True)


    async def _send_reply_card(self, message: IncomingMessage, text: str, title: str = "openrelay 回复") -> None:
        await self.messenger.send_interactive_card(
            message.chat_id,
            build_reply_card(text, title),
            reply_to_message_id=message.reply_to_message_id or ("" if self._is_card_action_message(message) else message.message_id),
            root_id=self._root_id_for_message(message),
        )

    async def _reply_final(self, message: IncomingMessage, text: str, streaming: FeishuStreamingSession | None) -> None:
        if streaming is not None and streaming.has_started():
            try:
                await streaming.close(text)
                return
            except Exception:
                LOGGER.exception("streaming close failed for event_id=%s", message.event_id)
        if self.config.feishu.stream_mode == "card":
            try:
                await self._send_reply_card(message, text, "openrelay 回复")
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

    def _build_help_text(self, session: SessionRecord) -> str:
        available_backends = self.available_backend_names()
        message_count = len(self.store.list_messages(session.session_id))
        context_lines = self.session_ux.build_context_lines(session, limit=2)
        context_preview = self.session_ux.build_context_preview(session, limit=2)
        lines = [
            "OpenRelay 帮助",
            "",
            "当前状态：",
            f"- 会话：{session.label or '未命名会话'} ({session.session_id})",
            f"- 会话阶段：{self._describe_help_session_phase(session, message_count)}",
            f"- 通道：{format_release_channel(infer_release_channel(self.config, session))}",
            f"- 目录：{self.session_ux.format_cwd(session.cwd, session)}",
            f"- 后端：{session.backend}",
            f"- 模型：{self.session_ux.effective_model(session)}",
            f"- sandbox：{session.safety_mode}",
            f"- 原生会话：{session.native_session_id or 'pending（直接发消息就会创建）'}",
            f"- 上下文占用：{self.session_ux.format_context_usage(session)}",
            f"- 本地消息数：{message_count}",
            f"- 最近关注：{context_preview or '还没有可总结的本地上下文'}",
            "",
            "一句话判断：",
            f"- {self._build_help_now_summary(session, message_count)}",
        ]
        context_note = self._build_help_context_note(session)
        if context_note:
            lines.append(context_note)
        lines.extend(
            [
                "",
                "你现在最该做什么：",
                *self._build_help_priority_actions(session, message_count),
                "",
                "下一条消息可以直接这样发：",
                *self._build_help_prompt_examples(session, message_count),
                "",
                "什么时候该用命令：",
                *self._build_help_command_guide(available_backends),
                "",
                "最近上下文：",
                *context_lines,
                "",
                "提示：如果目标没变，别先发命令，直接补充任务、报错、文件路径，或明确让它继续下一步。",
            ]
        )
        return "\n".join(lines)

    def _describe_help_session_phase(self, session: SessionRecord, message_count: int) -> str:
        if message_count == 0 and session.native_session_id:
            return "仅原生会话（可继续发消息，但本地暂未缓存上下文）"
        if message_count == 0:
            return "未开始（还没发第一条真实需求）"
        if session.native_session_id:
            return "进行中（继续发消息会沿用当前原生会话）"
        return "待启动（已有本地上下文，下一条真实消息会创建原生会话）"

    def _build_help_now_summary(self, session: SessionRecord, message_count: int) -> str:
        if message_count == 0 and session.native_session_id:
            return "这是一个已连接原生会话但本地上下文为空的会话；直接发消息会继续原会话。"
        if message_count == 0:
            return "这是一个空会话；最有效的动作通常是直接发完整任务，而不是先试很多命令。"
        if session.native_session_id:
            return "这是一个进行中的会话；如果任务没变，直接补充信息最快。"
        return "这是一个已有本地上下文但尚未重新连上原生执行的会话；下一条真实消息会自动接上。"

    def _build_help_context_note(self, session: SessionRecord) -> str | None:
        usage_ratio = self._help_context_usage_ratio(session)
        if usage_ratio is None:
            return None
        if usage_ratio >= 0.85:
            return "- 上下文提醒：当前上下文已经接近窗口上限；如果要开新任务，优先 /new，别继续混在这个会话里。"
        if usage_ratio >= 0.65:
            return "- 上下文提醒：当前上下文已经不短；如果话题要明显切换，建议先 /new 隔离。"
        return None

    def _help_context_usage_ratio(self, session: SessionRecord) -> float | None:
        usage = session.last_usage if isinstance(session.last_usage, dict) else {}
        total_tokens = usage.get("total_tokens")
        model_context_window = usage.get("model_context_window")
        try:
            total_value = int(total_tokens)
            window_value = int(model_context_window)
        except (TypeError, ValueError):
            return None
        if window_value <= 0:
            return None
        return total_value / window_value

    def _build_help_priority_actions(self, session: SessionRecord, message_count: int) -> list[str]:
        if message_count == 0 and session.native_session_id:
            return [
                "- 想延续上个原生会话：直接发消息，不需要先补命令。",
                "- 想改成新任务：先 /new <label>，再发新需求，避免旧上下文干扰。",
                "- 想先确认目录、模型、通道和最近上下文，发 /status。",
            ]
        if message_count == 0:
            return [
                "- 先把目标说完整：要改什么、在哪个目录、是否要直接改代码。",
                "- 有明确目录就先 /cwd <path>；没有就直接发任务，别把时间花在命令上。",
                "- 如果这是稳定版本排障，用 /main；如果是实验性修复，用 /develop。",
            ]
        if session.native_session_id:
            return [
                "- 如果还是同一件事，直接追加信息：目标、报错、文件路径、验收标准。",
                "- 如果你想让它立刻推进，直接说“继续，先做下一步并汇报改动”。",
                "- 如果任务已经变了，先 /new <label>，不要把新需求继续塞进当前会话。",
            ]
        return [
            "- 直接再发一条真实消息，系统会基于当前本地上下文重新接上执行。",
            "- 如果现在其实是新任务，先 /new <label> 隔离上下文。",
            "- 如果你要回到更早的某次对话，先 /resume list 再恢复。",
        ]

    def _build_help_prompt_examples(self, session: SessionRecord, message_count: int) -> list[str]:
        if message_count == 0 and session.native_session_id:
            return [
                '- “继续刚才那个任务，先回顾当前进度，再直接往下做。”',
                '- “不要开新话题，基于当前会话继续修这个问题：<描述>。”',
                '- “先告诉我你准备怎么继续，然后直接开始。”',
                '- “如果你判断这已经是新任务，提醒我先 /new，再继续。”',
            ]
        if message_count == 0:
            return [
                '- “先快速读一下这个仓库，告诉我入口、运行方式和关键目录。”',
                '- “定位这个报错的根因：<贴报错>; 先解释判断，再直接修复。”',
                '- “在 <path> 下实现 <需求>；先列计划，再按最小改动完成。”',
                '- “先不要改代码，帮我梳理实现方案、风险和验收点。”',
            ]
        if session.native_session_id:
            return [
                '- “继续刚才的任务，下一步先检查 <file/path>，然后直接改。”',
                '- “这个报错还在：<贴报错>; 结合当前上下文继续排查。”',
                '- “基于现在的进度继续，不要重来；做完告诉我改了哪些文件。”',
                '- “先别写代码，帮我总结当前进度、阻塞点和下一步。”',
            ]
        return [
            '- “基于当前上下文继续，先总结你理解的现状，再直接往下做。”',
            '- “把最近这个任务接上，先检查 <file/path>，然后继续实现。”',
            '- “如果当前上下文不足以继续，请明确告诉我缺什么信息。”',
            '- “先帮我整理当前上下文里的目标、已完成项和待做项。”',
        ]

    def _build_help_command_guide(self, available_backends: list[str]) -> list[str]:
        lines = [
            "- 同一任务继续干：通常不用命令，直接发消息。",
            "- 开新任务或切话题：/new <label>；回旧会话：/resume list、/resume latest。",
            "- 换执行位置：/cwd <path> 切目录；/main 回稳定工作区；/develop 进修复工作区。",
            "- 看现场：/status 看会话、目录、最近上下文；/usage 看 token 和 context_usage。",
            "- 控制运行：/stop 停止生成；/clear 清空当前上下文；/panel 打开会话面板。",
            "- 环境与维护：/model 切模型；/sandbox 切执行模式；/ping 连通性检查；/restart 管理员用。",
        ]
        if len(available_backends) > 1:
            lines.append(f"- 切后端：/backend [list|{'|'.join(available_backends)}]。")
        return lines

    def available_backend_names(self) -> list[str]:
        return sorted(self.backends)

    def _command_reply_target(self, message: IncomingMessage) -> str:
        return message.reply_to_message_id or ("" if self._is_card_action_message(message) else message.message_id)

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

    def _is_stop_command(self, text: str) -> bool:
        return text.strip().lower().startswith("/stop")

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
