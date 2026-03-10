from __future__ import annotations

from dataclasses import dataclass
import os
import shlex
from typing import Awaitable, Callable

from openrelay.config import AppConfig, SAFETY_MODES
from openrelay.help_renderer import HelpRenderer
from openrelay.models import IncomingMessage, SessionRecord
from openrelay.release import format_release_channel, get_session_workspace_root, infer_release_channel, read_release_events, summarize_release_event
from openrelay.session_browser import DEFAULT_SESSION_LIST_SORT, DEFAULT_SESSION_LIST_PAGE_SIZE, SessionBrowser, SessionSortMode
from openrelay.session_ux import SessionUX
from openrelay.state import StateStore


ADMIN_ONLY_COMMANDS = {"/restart"}
RESUME_USAGE = "使用 /resume [list|latest|<序号>|<session_id>] [--page N] [--sort updated-desc|active-first]。"

ReplyHook = Callable[..., Awaitable[None]]
SendHelpHook = Callable[[IncomingMessage, str, SessionRecord], Awaitable[None]]
SendPanelHook = Callable[[IncomingMessage, str, SessionRecord], Awaitable[None]]
SendSessionListHook = Callable[[IncomingMessage, str, SessionRecord, int, SessionSortMode], Awaitable[None]]
SwitchReleaseHook = Callable[[IncomingMessage, str, SessionRecord, str, str, str], Awaitable[None]]
StopHook = Callable[[IncomingMessage, str], Awaitable[None]]
ScheduleRestartHook = Callable[[], None]
IsAdminHook = Callable[[str], bool]
AvailableBackendsHook = Callable[[], list[str]]


@dataclass(slots=True)
class RuntimeCommandHooks:
    reply: ReplyHook
    send_help: SendHelpHook
    send_panel: SendPanelHook
    send_session_list: SendSessionListHook
    switch_release_channel: SwitchReleaseHook
    stop: StopHook
    schedule_restart: ScheduleRestartHook
    is_admin: IsAdminHook
    available_backend_names: AvailableBackendsHook


@dataclass(slots=True)
class ResumeCommandArgs:
    target: str
    page: int
    sort_mode: SessionSortMode


class RuntimeCommandRouter:
    def __init__(
        self,
        config: AppConfig,
        store: StateStore,
        session_browser: SessionBrowser,
        session_ux: SessionUX,
        help_renderer: HelpRenderer,
        backends: dict[str, object],
        hooks: RuntimeCommandHooks,
    ):
        self.config = config
        self.store = store
        self.session_browser = session_browser
        self.session_ux = session_ux
        self.help_renderer = help_renderer
        self.backends = backends
        self.hooks = hooks

    async def handle(self, message: IncomingMessage, session_key: str, session: SessionRecord) -> bool:
        raw = message.text.strip()
        if not raw.startswith("/"):
            return False
        parts = raw.split(maxsplit=1)
        name = parts[0].lower()
        arg_text = parts[1].strip() if len(parts) > 1 else ""

        if name in ADMIN_ONLY_COMMANDS and not self.hooks.is_admin(message.sender_open_id):
            await self.hooks.reply(message, "这个命令只允许管理员使用。", command_reply=True)
            return True

        if name == "/ping":
            await self.hooks.reply(message, "pong", command_reply=True)
            return True

        if name in {"/help", "/tools"}:
            await self.hooks.send_help(message, session_key, session)
            return True

        if name == "/panel":
            await self.hooks.send_panel(message, session_key, session)
            return True

        if name == "/restart":
            await self.hooks.reply(message, "正在重启 openrelay，预计几秒后恢复。", command_reply=True)
            self.hooks.schedule_restart()
            return True

        if name in {"/main", "/stable", "/develop"}:
            target_channel = "develop" if name == "/develop" else "main"
            await self.hooks.switch_release_channel(message, session_key, session, target_channel, name, arg_text)
            return True

        if name == "/new":
            next_session = self.store.create_next_session(session_key, session, arg_text)
            label = f" ({next_session.label})" if next_session.label else ""
            await self.hooks.reply(message, f"已新建会话 {next_session.session_id}{label}，原生 Codex 会话会在首条真实消息时创建。", command_reply=True)
            return True

        if name == "/clear":
            next_session = self.store.create_next_session(session_key, session, session.label)
            next_session.model_override = session.model_override
            next_session.safety_mode = session.safety_mode
            next_session.release_channel = session.release_channel
            self.store.save_session(next_session)
            await self.hooks.reply(message, f"已清空当前上下文，新的会话是 {next_session.session_id}。", command_reply=True)
            return True

        if name == "/model":
            if not arg_text:
                await self.hooks.reply(message, f"model={self.session_ux.effective_model(session)}", command_reply=True)
                return True
            next_session = self.store.create_next_session(session_key, session, session.label)
            next_session.model_override = "" if arg_text.lower() in {"default", "reset", "clear"} else arg_text
            self.store.save_session(next_session)
            await self.hooks.reply(message, f"model 已切换到 {self.session_ux.effective_model(next_session)}，新的原生会话会在首条真实消息时创建。", command_reply=True)
            return True

        if name in {"/sandbox", "/mode"}:
            if not arg_text:
                await self.hooks.reply(message, f"sandbox={session.safety_mode}", command_reply=True)
                return True
            mode = arg_text.lower()
            if mode not in SAFETY_MODES:
                await self.hooks.reply(message, "sandbox 仅支持：read-only / workspace-write / danger-full-access", command_reply=True)
                return True
            if mode == "danger-full-access" and not self.hooks.is_admin(message.sender_open_id):
                await self.hooks.reply(message, "danger-full-access 只允许管理员切换。", command_reply=True)
                return True
            next_session = self.store.create_next_session(session_key, session, session.label)
            next_session.safety_mode = mode
            self.store.save_session(next_session)
            await self.hooks.reply(message, f"sandbox 已切换到 {next_session.safety_mode}，新的原生会话会在首条真实消息时创建。", command_reply=True)
            return True

        if name == "/resume":
            return await self._handle_resume(message, session_key, session, arg_text)

        if name == "/reset":
            self.store.clear_sessions(session_key)
            self.store.load_session(session_key)
            await self.hooks.reply(message, "会话已重置。", command_reply=True)
            return True

        if name in {"/status", "/usage"}:
            await self.hooks.reply(message, self._build_status_text(name, session_key, session), command_reply=True, command_name=name)
            return True

        if name in {"/cwd", "/cd"}:
            return await self._handle_cwd(name, arg_text, message, session_key, session)

        if name == "/backend":
            return await self._handle_backend(message, session_key, session, arg_text)

        if name == "/stop":
            await self.hooks.stop(message, session_key)
            return True

        await self.hooks.reply(message, f"本地命令未实现：{name}。发送 /help 查看可用命令。", command_reply=True)
        return True

    async def _handle_resume(self, message: IncomingMessage, session_key: str, session: SessionRecord, arg_text: str) -> bool:
        try:
            args = self._parse_resume_command_args(arg_text)
        except ValueError as exc:
            await self.hooks.reply(message, f"resume 参数无效：{exc}\n{RESUME_USAGE}", command_reply=True, command_name="/resume")
            return True

        if not args.target or args.target.lower() == "list":
            await self.hooks.send_session_list(message, session_key, session, args.page, args.sort_mode)
            return True

        merged_sessions = self.session_browser.list_entries(session_key, session, limit=max(50, args.page * DEFAULT_SESSION_LIST_PAGE_SIZE + 1), sort_mode=args.sort_mode)
        resumed = self.session_browser.resume(session_key, session, args.target, merged_sessions)
        if resumed is None:
            fallback_page = self.session_browser.list_page(session_key, session, page=args.page, page_size=DEFAULT_SESSION_LIST_PAGE_SIZE, sort_mode=args.sort_mode)
            await self.hooks.reply(message, f"恢复失败。\n\n{self.session_ux.format_session_list_page(fallback_page)}", command_reply=True)
            return True
        await self.hooks.reply(message, self.session_ux.format_resume_success(resumed.session, imported=resumed.imported, entry=resumed.entry), command_reply=True)
        return True

    def _parse_resume_command_args(self, arg_text: str) -> ResumeCommandArgs:
        tokens = shlex.split(arg_text) if arg_text else []
        target = ""
        page = 1
        sort_mode = DEFAULT_SESSION_LIST_SORT
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token == "--page":
                index += 1
                if index >= len(tokens):
                    raise ValueError("--page 缺少页码")
                page = self._parse_positive_int(tokens[index], "page")
            elif token.startswith("--page="):
                page = self._parse_positive_int(token.split("=", 1)[1], "page")
            elif token == "--sort":
                index += 1
                if index >= len(tokens):
                    raise ValueError("--sort 缺少排序模式")
                sort_mode = self.session_browser.normalize_sort_mode(tokens[index])
            elif token.startswith("--sort="):
                sort_mode = self.session_browser.normalize_sort_mode(token.split("=", 1)[1])
            elif token.startswith("--"):
                raise ValueError(f"不支持的选项：{token}")
            elif not target:
                target = token
            else:
                raise ValueError(f"多余参数：{token}")
            index += 1
        return ResumeCommandArgs(target=target, page=page, sort_mode=sort_mode)

    def _parse_positive_int(self, value: str, name: str) -> int:
        try:
            parsed = int(value)
        except ValueError as exc:
            raise ValueError(f"{name} 必须是正整数") from exc
        if parsed <= 0:
            raise ValueError(f"{name} 必须是正整数")
        return parsed

    async def _handle_cwd(self, command_name: str, arg_text: str, message: IncomingMessage, session_key: str, session: SessionRecord) -> bool:
        if not arg_text:
            await self.hooks.reply(
                message,
                "\n".join([
                    f"cwd={self.session_ux.format_cwd(session.cwd, session)}",
                    "切换目录：/cwd <path> 或 /cd <path>",
                    "切目录时会创建一个新的空会话；旧会话历史仍可通过 /resume 找回。",
                ]),
                command_reply=True,
                command_name=command_name,
            )
            return True
        try:
            next_cwd = self.session_ux.resolve_cwd(session.cwd, arg_text, session)
        except ValueError as exc:
            await self.hooks.reply(message, f"cwd 切换失败：{exc}", command_reply=True, command_name=command_name)
            return True
        next_session = self.store.create_next_session(session_key, session, session.label)
        next_session.cwd = str(next_cwd)
        next_session.native_session_id = ""
        self.store.save_session(next_session)
        await self.hooks.reply(
            message,
            "\n".join([
                f"cwd 已切换到 {self.session_ux.format_cwd(next_session.cwd, next_session)}。",
                "现在直接发消息，就会在这个目录进入 Codex。",
                "已创建新的空会话；原会话历史还在，想回来可以 /resume list。",
            ]),
            command_reply=True,
            command_name=command_name,
        )
        return True

    async def _handle_backend(self, message: IncomingMessage, session_key: str, session: SessionRecord, arg_text: str) -> bool:
        available = self.hooks.available_backend_names()
        if not arg_text or arg_text.lower() == "list":
            await self.hooks.reply(message, "\n".join([f"backend={session.backend}", f"available={', '.join(available)}"]), command_reply=True)
            return True
        backend = arg_text.lower()
        if backend not in self.backends:
            await self.hooks.reply(message, f"backend 仅支持：{', '.join(available)}", command_reply=True)
            return True
        next_session = self.store.create_next_session(session_key, session, session.label)
        next_session.backend = backend
        next_session.native_session_id = ""
        self.store.save_session(next_session)
        await self.hooks.reply(message, f"backend 已切换到 {backend}，新的原生会话将在下一条真实消息时创建。", command_reply=True)
        return True

    def _build_status_text(self, command_name: str, session_key: str, session: SessionRecord) -> str:
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
        if command_name == "/status":
            lines.extend(["", "最近上下文：", *self.session_ux.build_context_lines(session)])
        return "\n".join(lines)
