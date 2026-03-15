from __future__ import annotations

from dataclasses import dataclass
import os
import shlex
from typing import Awaitable, Callable, Literal

from openrelay.core import (
    SAFETY_MODES,
    AppConfig,
    DirectoryShortcut,
    IncomingMessage,
    SessionRecord,
    format_release_channel,
    get_session_workspace_root,
    infer_release_channel,
    read_release_events,
    summarize_release_event,
)
from openrelay.release import ReleaseCommandService
from openrelay.session import (
    DEFAULT_SESSION_LIST_PAGE_SIZE,
    DEFAULT_SESSION_LIST_SORT,
    SessionBrowser,
    SessionMutationService,
    SessionSortMode,
    SessionUX,
    SessionWorkspaceService,
)
from openrelay.storage import StateStore

from .help import HelpRenderer


ADMIN_ONLY_COMMANDS = {"/restart"}
PANEL_USAGE = "使用 /panel [sessions|directories|commands|status] [--page N] [--sort updated-desc|active-first]。"
RESUME_USAGE = "使用 /resume [list|latest|<序号>|<session_id>] [--page N] [--sort updated-desc|active-first]。"
SHORTCUT_USAGE = (
    "使用 /shortcut list | /shortcut add <name> <path> [all|main|develop] | "
    "/shortcut remove <name> | /shortcut cd <name>。"
)

ReplyHook = Callable[..., Awaitable[None]]
SendHelpHook = Callable[[IncomingMessage, str, SessionRecord], Awaitable[None]]
SendPanelHook = Callable[[IncomingMessage, str, SessionRecord, "PanelCommandArgs"], Awaitable[None]]
SendSessionListHook = Callable[[IncomingMessage, str, SessionRecord, int, SessionSortMode], Awaitable[None]]
StopHook = Callable[[IncomingMessage, str], Awaitable[None]]
ScheduleRestartHook = Callable[[], None]
IsAdminHook = Callable[[str], bool]
AvailableBackendsHook = Callable[[], list[str]]
CancelActiveRunHook = Callable[[SessionRecord, str], Awaitable[bool]]

PanelView = Literal["home", "sessions", "directories", "commands", "status"]


@dataclass(slots=True)
class RuntimeCommandHooks:
    reply: ReplyHook
    send_help: SendHelpHook
    send_panel: SendPanelHook
    send_session_list: SendSessionListHook
    stop: StopHook
    schedule_restart: ScheduleRestartHook
    is_admin: IsAdminHook
    available_backend_names: AvailableBackendsHook
    cancel_active_run_for_session: CancelActiveRunHook


@dataclass(slots=True)
class ResumeCommandArgs:
    target: str
    page: int
    sort_mode: SessionSortMode


@dataclass(slots=True)
class PanelCommandArgs:
    view: PanelView
    page: int
    sort_mode: SessionSortMode


@dataclass(slots=True)
class PagingCommandArgs:
    target: str
    page: int
    sort_mode: SessionSortMode


class RuntimeCommandRouter:
    def __init__(
        self,
        config: AppConfig,
        store: StateStore,
        session_browser: SessionBrowser,
        session_mutations: SessionMutationService,
        session_ux: SessionUX,
        workspace: SessionWorkspaceService,
        help_renderer: HelpRenderer,
        release_commands: ReleaseCommandService,
        backends: dict[str, object],
        hooks: RuntimeCommandHooks,
    ):
        self.config = config
        self.store = store
        self.session_browser = session_browser
        self.session_mutations = session_mutations
        self.session_ux = session_ux
        self.workspace = workspace
        self.help_renderer = help_renderer
        self.release_commands = release_commands
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
            try:
                args = self._parse_panel_command_args(arg_text)
            except ValueError as exc:
                await self.hooks.reply(message, f"panel 参数无效：{exc}\n{PANEL_USAGE}", command_reply=True, command_name="/panel")
                return True
            await self.hooks.send_panel(message, session_key, session, args)
            return True

        if name == "/restart":
            await self.hooks.reply(message, "正在重启 openrelay，预计几秒后恢复。", command_reply=True)
            self.hooks.schedule_restart()
            return True

        if name in {"/main", "/stable", "/develop"}:
            target_channel = "develop" if name == "/develop" else "main"
            await self._handle_release_switch(message, session_key, session, target_channel, name, arg_text)
            return True

        if name == "/new":
            if not self._can_use_top_level_session_command(message):
                await self.hooks.reply(message, "`/new` 只允许在私聊顶层使用；子 thread 会固定绑定当前 Codex 会话。", command_reply=True)
                return True
            next_session = self.session_mutations.create_named_session(self._top_level_thread_scope_key(message), session, arg_text)
            label = f" ({next_session.label})" if next_session.label else ""
            await self.hooks.reply(message, f"已新建会话 {next_session.session_id}{label}，原生 Codex 会话会在首条真实消息时创建。", command_reply=True)
            return True

        if name == "/clear":
            next_session = self.session_mutations.clear_context(session_key, session)
            await self.hooks.reply(message, f"已清空当前上下文，新的会话是 {next_session.session_id}。", command_reply=True)
            return True

        if name == "/model":
            if not arg_text:
                await self.hooks.reply(message, f"model={self.session_ux.effective_model(session)}", command_reply=True)
                return True
            next_session = self.session_mutations.switch_model(
                session_key,
                session,
                "" if arg_text.lower() in {"default", "reset", "clear"} else arg_text,
            )
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
            next_session = self.session_mutations.switch_sandbox(session_key, session, mode)
            await self.hooks.reply(message, f"sandbox 已切换到 {next_session.safety_mode}，新的原生会话会在首条真实消息时创建。", command_reply=True)
            return True

        if name == "/resume":
            return await self._handle_resume(message, session_key, session, arg_text)

        if name == "/reset":
            self.session_mutations.reset_scope(session_key)
            await self.hooks.reply(message, "会话已重置。", command_reply=True)
            return True

        if name in {"/status", "/usage"}:
            await self.hooks.reply(message, self._build_status_text(name, session_key, session), command_reply=True, command_name=name)
            return True

        if name in {"/cwd", "/cd"}:
            return await self._handle_cwd(name, arg_text, message, session_key, session)

        if name in {"/shortcut", "/shortcuts"}:
            return await self._handle_shortcut(message, session_key, session, arg_text)

        if name == "/backend":
            return await self._handle_backend(message, session_key, session, arg_text)

        if name == "/stop":
            await self.hooks.stop(message, session_key)
            return True

        await self.hooks.reply(message, f"本地命令未实现：{name}。发送 /help 查看可用命令。", command_reply=True)
        return True

    async def _handle_resume(self, message: IncomingMessage, session_key: str, session: SessionRecord, arg_text: str) -> bool:
        if not self._can_use_top_level_session_command(message):
            await self.hooks.reply(message, "`/resume` 只允许在私聊顶层使用；子 thread 会固定绑定当前 Codex 会话。", command_reply=True, command_name="/resume")
            return True
        try:
            args = self._parse_resume_command_args(arg_text)
        except ValueError as exc:
            await self.hooks.reply(message, f"resume 参数无效：{exc}\n{RESUME_USAGE}", command_reply=True, command_name="/resume")
            return True

        scope_key = self._top_level_thread_scope_key(message)
        if not args.target or args.target.lower() == "list":
            await self.hooks.send_session_list(message, session_key, session, args.page, args.sort_mode)
            return True

        merged_sessions = self.session_browser.list_entries(scope_key, session, limit=max(50, args.page * DEFAULT_SESSION_LIST_PAGE_SIZE + 1), sort_mode=args.sort_mode)
        resumed = self.session_browser.resume(scope_key, session, args.target, merged_sessions)
        if resumed is None:
            fallback_page = self.session_browser.list_page(session_key, session, page=args.page, page_size=DEFAULT_SESSION_LIST_PAGE_SIZE, sort_mode=args.sort_mode)
            await self.hooks.reply(message, f"恢复失败。\n\n{self.session_ux.format_session_list_page(fallback_page)}", command_reply=True)
            return True
        await self.hooks.reply(message, self.session_ux.format_resume_success(resumed.session, entry=resumed.entry), command_reply=True)
        return True

    def _is_top_level_p2p_command(self, message: IncomingMessage) -> bool:
        return message.chat_type == "p2p" and not message.root_id and not message.thread_id

    def _is_card_action_message(self, message: IncomingMessage) -> bool:
        return message.event_id.startswith("card-action-")

    def _can_use_top_level_session_command(self, message: IncomingMessage) -> bool:
        return self._is_top_level_p2p_command(message) or self._is_card_action_message(message)

    def _top_level_thread_scope_key(self, message: IncomingMessage) -> str:
        return f"p2p:{message.chat_id}:thread:{message.message_id}"

    def _parse_resume_command_args(self, arg_text: str) -> ResumeCommandArgs:
        args = self._parse_paging_command_args(arg_text)
        return ResumeCommandArgs(target=args.target, page=args.page, sort_mode=args.sort_mode)

    def _parse_panel_command_args(self, arg_text: str) -> PanelCommandArgs:
        args = self._parse_paging_command_args(arg_text)
        uses_session_paging = args.page != 1 or args.sort_mode != DEFAULT_SESSION_LIST_SORT
        view = self._normalize_panel_view(args.target or ("sessions" if uses_session_paging else "home"))
        if view != "sessions" and uses_session_paging:
            raise ValueError("只有 /panel sessions 支持 --page 和 --sort")
        return PanelCommandArgs(view=view, page=args.page, sort_mode=args.sort_mode)

    def _parse_paging_command_args(self, arg_text: str) -> PagingCommandArgs:
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
        return PagingCommandArgs(target=target, page=page, sort_mode=sort_mode)

    def _normalize_panel_view(self, value: str) -> PanelView:
        aliases: dict[str, PanelView] = {
            "": "home",
            "home": "home",
            "overview": "home",
            "main": "home",
            "session": "sessions",
            "sessions": "sessions",
            "list": "sessions",
            "directory": "directories",
            "directories": "directories",
            "dir": "directories",
            "dirs": "directories",
            "command": "commands",
            "commands": "commands",
            "action": "commands",
            "actions": "commands",
            "status": "status",
            "state": "status",
        }
        normalized = value.strip().lower()
        if normalized in aliases:
            return aliases[normalized]
        raise ValueError(f"不支持的 panel 视图：{value}")

    def _parse_positive_int(self, value: str, name: str) -> int:
        try:
            parsed = int(value)
        except ValueError as exc:
            raise ValueError(f"{name} 必须是正整数") from exc
        if parsed <= 0:
            raise ValueError(f"{name} 必须是正整数")
        return parsed

    async def _handle_release_switch(
        self,
        message: IncomingMessage,
        session_key: str,
        session: SessionRecord,
        target_channel: str,
        command_name: str,
        reason: str,
    ) -> None:
        cancelled_active_run = await self.hooks.cancel_active_run_for_session(session, command_name)
        try:
            result = self.release_commands.switch_channel(
                session_key=session_key,
                session=session,
                target_channel=target_channel,
                command_name=command_name,
                reason=reason,
                chat_id=message.chat_id,
                operator_open_id=message.sender_open_id,
                cancelled_active_run=cancelled_active_run,
            )
        except FileNotFoundError as exc:
            await self.hooks.reply(message, str(exc), command_reply=True)
            return
        await self.hooks.reply(
            message,
            "\n".join(
                filter(
                    None,
                    [
                        "已强制切到 main 稳定版本。" if target_channel == "main" else "已切到 develop 修复版本。",
                        f"session_id={result.session.session_id}",
                        f"channel={format_release_channel(target_channel)}",
                        f"cwd={self.session_ux.format_cwd(result.session.cwd, result.session)}",
                        f"sandbox={result.session.safety_mode}",
                        f"reason={reason}" if reason else "",
                        "已中断上一条进行中的回复。" if result.cancelled_active_run else "",
                        "已写入切换记录，后续智能体可据此继续修复。",
                    ],
                )
            ),
            command_reply=True,
        )

    async def _handle_cwd(self, command_name: str, arg_text: str, message: IncomingMessage, session_key: str, session: SessionRecord) -> bool:
        if not arg_text:
            await self.hooks.reply(
                message,
                "\n".join([
                    f"cwd={self.workspace.format_cwd(session.cwd, session)}",
                    "切换目录：/cwd <path> 或 /cd <path>",
                    "切目录时会创建一个新的空会话；旧会话历史仍可通过 /resume 找回。",
                ]),
                command_reply=True,
                command_name=command_name,
            )
            return True
        try:
            next_cwd = self.workspace.resolve_cwd(session.cwd, arg_text, session)
        except ValueError as exc:
            await self.hooks.reply(message, f"cwd 切换失败：{exc}", command_reply=True, command_name=command_name)
            return True
        next_session = self.session_mutations.switch_cwd(session_key, session, next_cwd)
        await self.hooks.reply(
            message,
            "\n".join([
                f"cwd 已切换到 {self.workspace.format_cwd(next_session.cwd, next_session)}。",
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
        next_session = self.session_mutations.switch_backend(session_key, session, backend)
        await self.hooks.reply(message, f"backend 已切换到 {backend}，新的原生会话将在下一条真实消息时创建。", command_reply=True)
        return True

    async def _handle_shortcut(self, message: IncomingMessage, session_key: str, session: SessionRecord, arg_text: str) -> bool:
        tokens = shlex.split(arg_text) if arg_text else []
        action = tokens[0].lower() if tokens else "list"

        if action in {"list", "ls"}:
            shortcuts = self.session_mutations.list_directory_shortcuts(session, limit=100)
            if not shortcuts:
                await self.hooks.reply(
                    message,
                    "当前没有可用的快捷目录。\n\n先用 `/shortcut add <name> <path>` 新增一个，或直接 `/cwd <path>`。",
                    command_reply=True,
                    command_name="/shortcut",
                )
                return True
            lines = ["快捷目录："]
            for entry in shortcuts:
                lines.append(f"- {entry['label']} -> {entry['display_path']} [{entry['channels']}]")
            lines.extend(["", "快速切换：/shortcut cd <name>"])
            await self.hooks.reply(message, "\n".join(lines), command_reply=True, command_name="/shortcut")
            return True

        if action == "add":
            try:
                shortcut = self._parse_shortcut_add(tokens[1:])
            except ValueError as exc:
                await self.hooks.reply(message, f"shortcut 参数无效：{exc}\n{SHORTCUT_USAGE}", command_reply=True, command_name="/shortcut")
                return True
            self.session_mutations.save_directory_shortcut(shortcut)
            await self.hooks.reply(
                message,
                "\n".join(
                    [
                        f"已保存快捷目录 `{shortcut.name}`。",
                        f"path={shortcut.path}",
                        f"channels={','.join(shortcut.channels)}",
                        f"使用 `/shortcut cd {shortcut.name}` 或 `/panel directories`。",
                    ]
                ),
                command_reply=True,
                command_name="/shortcut",
            )
            return True

        if action in {"remove", "rm", "del", "delete"}:
            name = tokens[1].strip() if len(tokens) > 1 else ""
            if not name:
                await self.hooks.reply(message, f"shortcut 参数无效：缺少名称\n{SHORTCUT_USAGE}", command_reply=True, command_name="/shortcut")
                return True
            removed = self.session_mutations.remove_directory_shortcut(name)
            if removed:
                await self.hooks.reply(message, f"已删除快捷目录 `{name}`。", command_reply=True, command_name="/shortcut")
                return True
            await self.hooks.reply(message, f"没有找到可删除的快捷目录：`{name}`。", command_reply=True, command_name="/shortcut")
            return True

        if action in {"cd", "go", "use"}:
            name = tokens[1].strip() if len(tokens) > 1 else ""
            if not name:
                await self.hooks.reply(message, f"shortcut 参数无效：缺少名称\n{SHORTCUT_USAGE}", command_reply=True, command_name="/shortcut")
                return True
            target = self.session_mutations.resolve_directory_shortcut(name, session)
            if target is None:
                await self.hooks.reply(
                    message,
                    f"没有找到当前通道可用的快捷目录：`{name}`。\n先发 `/shortcut list` 看可用入口。",
                    command_reply=True,
                    command_name="/shortcut",
                )
                return True
            return await self._handle_cwd("/shortcut", str(target), message, session_key, session)

        await self.hooks.reply(message, f"shortcut 参数无效：不支持的动作 `{action}`\n{SHORTCUT_USAGE}", command_reply=True, command_name="/shortcut")
        return True

    def _parse_shortcut_add(self, tokens: list[str]) -> DirectoryShortcut:
        if len(tokens) < 2:
            raise ValueError("add 需要 <name> <path>")
        name = tokens[0].strip()
        path = tokens[1].strip()
        if not name:
            raise ValueError("name 不能为空")
        if not path:
            raise ValueError("path 不能为空")
        channels: tuple[str, ...] = ("all",)
        if len(tokens) >= 3:
            channel = tokens[2].strip().lower()
            if channel not in {"all", "main", "develop"}:
                raise ValueError("channels 仅支持 all / main / develop")
            channels = (channel,)
        if len(tokens) > 3:
            raise ValueError("add 最多支持一个 channels 参数")
        return DirectoryShortcut(name=name, path=path, channels=channels)

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
            f"backend_thread={session.native_session_id or 'pending'}",
            f"release_log={self.config.data_dir / 'release-events.jsonl'}",
            f"server_pid={os.getpid()}",
            f"last_release_event={summarize_release_event(latest_release_event[0]) if latest_release_event else 'none'}",
        ]
        lines.extend(self.session_ux.build_usage_lines(session))
        if command_name == "/status":
            lines.extend(["", "最近上下文：", *self.session_ux.build_context_lines(session)])
        return "\n".join(lines)
