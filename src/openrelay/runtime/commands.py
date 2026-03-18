from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shlex
from typing import Awaitable, Callable, Literal

from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.agent_runtime import ListSessionsRequest, SessionLocator
from openrelay.core import (
    SAFETY_MODES,
    AppConfig,
    DirectoryShortcut,
    IncomingMessage,
    SessionRecord,
    format_release_channel,
)
from openrelay.presentation.runtime_status import RuntimeStatusPresenter
from openrelay.presentation.session import SessionPresentation
from openrelay.release import ReleaseCommandService
from openrelay.session import (
    DEFAULT_SESSION_LIST_PAGE_SIZE,
    DEFAULT_SESSION_LIST_SORT,
    SessionBrowser,
    SessionMutationService,
    SessionScopeResolver,
    SessionShortcutService,
    SessionSortMode,
    SessionWorkspaceService,
)
from openrelay.storage import StateStore

from .help import HelpRenderer


ADMIN_ONLY_COMMANDS = {"/restart"}
RESUME_USAGE = "使用 /resume 打开后端会话卡片，或 /resume [latest|<序号>|<session_id>|<local_session_id>] 直接连接。"
SHORTCUT_USAGE = (
    "使用 /shortcut list | /shortcut add <name> <path> [all|main|develop] | "
    "/shortcut remove <name> | /shortcut use <name>。"
)

ReplyHook = Callable[..., Awaitable[None]]
SendHelpHook = Callable[[IncomingMessage, str, SessionRecord, list[str]], Awaitable[None]]
SendPanelHook = Callable[[IncomingMessage, str, SessionRecord, "PanelCommandArgs"], Awaitable[None]]
SendSessionListHook = Callable[[IncomingMessage, str, SessionRecord, int, SessionSortMode], Awaitable[None]]
StopHook = Callable[[IncomingMessage, str], Awaitable[None]]
ScheduleRestartHook = Callable[[], None]
IsAdminHook = Callable[[str], bool]
AvailableBackendsHook = Callable[[], list[str]]
CancelActiveRunHook = Callable[[SessionRecord, str], Awaitable[bool]]

PanelView = Literal["home", "sessions", "workspace", "commands", "status"]


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
    target_path: str = ""
    query: str = ""


@dataclass(slots=True)
class PagingCommandArgs:
    target: str
    page: int
    sort_mode: SessionSortMode
    target_path: str = ""
    query: str = ""


@dataclass(slots=True)
class RuntimeSessionSummary:
    session_id: str
    preview: str
    cwd: str
    updated_at: str
    status: str
    name: str


@dataclass(slots=True)
class RuntimeTranscriptMessage:
    role: str
    text: str


@dataclass(slots=True)
class RuntimeSessionDetails:
    session_id: str
    preview: str
    cwd: str
    updated_at: str
    status: str
    name: str
    messages: tuple[RuntimeTranscriptMessage, ...]


class RuntimeCommandRouter:
    def __init__(
        self,
        config: AppConfig,
        store: StateStore,
        session_browser: SessionBrowser,
        session_scope: SessionScopeResolver,
        session_mutations: SessionMutationService,
        session_presentation: SessionPresentation,
        workspace: SessionWorkspaceService,
        shortcuts: SessionShortcutService,
        help_renderer: HelpRenderer,
        release_commands: ReleaseCommandService,
        status_presenter: RuntimeStatusPresenter,
        hooks: RuntimeCommandHooks,
        runtime_service: AgentRuntimeService | None = None,
    ):
        self.config = config
        self.store = store
        self.session_browser = session_browser
        self.session_scope = session_scope
        self.session_mutations = session_mutations
        self.session_presentation = session_presentation
        self.workspace = workspace
        self.shortcuts = shortcuts
        self.help_renderer = help_renderer
        self.release_commands = release_commands
        self.status_presenter = status_presenter
        self.runtime_service = runtime_service
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
            await self.hooks.send_help(message, session_key, session, self.hooks.available_backend_names())
            return True

        if name == "/panel":
            await self.hooks.reply(
                message,
                "`/panel` 已移除；恢复历史会话请用 `/resume`，切工作区请用 `/workspace`，查看现场请用 `/status`。",
                command_reply=True,
                command_name="/panel",
            )
            return True

        if name == "/restart":
            await self.hooks.reply(message, "正在重启 openrelay，预计几秒后恢复。", command_reply=True)
            self.hooks.schedule_restart()
            return True

        if name in {"/main", "/stable", "/develop"}:
            target_channel = "develop" if name == "/develop" else "main"
            await self._handle_release_switch(message, session_key, session, target_channel, name, arg_text)
            return True

        if name == "/clear":
            self.session_mutations.clear_context(session_key, session)
            await self.hooks.reply(message, "已清空当前上下文；当前 scope 保留原目录和配置。", command_reply=True)
            return True

        if name == "/model":
            if not arg_text:
                await self.hooks.reply(message, f"model={self.session_presentation.effective_model(session)}", command_reply=True)
                return True
            next_session = self.session_mutations.switch_model(
                session_key,
                session,
                "" if arg_text.lower() in {"default", "reset", "clear"} else arg_text,
            )
            await self.hooks.reply(message, f"model 已切换到 {self.session_presentation.effective_model(next_session)}；当前 scope 会从下一条真实消息开始使用新 thread。", command_reply=True)
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
            await self.hooks.reply(message, f"sandbox 已切换到 {next_session.safety_mode}；当前 scope 会从下一条真实消息开始使用新 thread。", command_reply=True)
            return True

        if name == "/resume":
            return await self._handle_resume(message, session_key, session, arg_text)

        if name == "/compact":
            return await self._handle_compact(message, session_key, session, arg_text)

        if name == "/reset":
            self.session_mutations.reset_scope(session_key)
            await self.hooks.reply(message, "会话已重置。", command_reply=True)
            return True

        if name in {"/status", "/usage"}:
            await self.hooks.reply(message, self.status_presenter.build_text(name, session_key, session), command_reply=True, command_name=name)
            return True

        if name in {"/workspace", "/ws"}:
            return await self._handle_workspace(message, session_key, session, arg_text)

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
            await self.hooks.reply(message, "`/resume` 只允许在私聊顶层使用；子 thread 会固定绑定当前后端会话。", command_reply=True, command_name="/resume")
            return True
        try:
            args = self._parse_resume_command_args(arg_text)
        except ValueError as exc:
            await self.hooks.reply(message, f"resume 参数无效：{exc}\n{RESUME_USAGE}", command_reply=True, command_name="/resume")
            return True

        scope_key = self._top_level_thread_scope_key(message)
        if not self._supports_runtime_session_listing(session):
            await self.hooks.reply(message, "当前后端不支持 `/resume` 原生命令。", command_reply=True, command_name="/resume")
            return True
        if not args.target:
            await self.hooks.send_session_list(message, session_key, session, args.page, args.sort_mode)
            return True
        target_session_id = await self._resolve_resume_session_id(session_key, session, args.target, args.page)
        if not target_session_id:
            await self.hooks.reply(message, "没有找到可连接的后端会话。先发 `/resume` 查看可用会话。", command_reply=True, command_name="/resume")
            return True
        runtime_session = await self._read_runtime_session(session, target_session_id)
        resumed_session = self.session_mutations.bind_native_thread(
            scope_key,
            session,
            runtime_session.session_id,
            cwd=runtime_session.cwd or session.cwd,
            label=runtime_session.name or session.label,
        )
        await self.hooks.reply(
            message,
            self._format_runtime_session_resume_success(resumed_session, runtime_session),
            command_reply=True,
            command_name="/resume",
        )
        return True

    async def _handle_compact(self, message: IncomingMessage, session_key: str, session: SessionRecord, arg_text: str) -> bool:
        if not self._supports_runtime_compact(session):
            await self.hooks.reply(message, "当前后端不支持 `/compact` 原生命令。", command_reply=True, command_name="/compact")
            return True
        cancelled_active_run = await self.hooks.cancel_active_run_for_session(session, "/compact")
        target = arg_text.strip()
        session_id = session.native_session_id
        if target:
            session_id = await self._resolve_resume_session_id(session_key, session, target, page=1)
        if not session_id:
            await self.hooks.reply(message, "当前没有可 compact 的后端会话。先恢复一个会话，或先发一条真实消息创建会话。", command_reply=True, command_name="/compact")
            return True
        result = await self._compact_runtime_session(session, session_id)
        compact_id = str(result.get("compactId") or result.get("id") or "").strip()
        lines = [f"{session.backend} compact 已完成：{session_id}"]
        if compact_id:
            lines.append(f"compact_id={compact_id}")
        if cancelled_active_run:
            lines.append("已先中断上一条进行中的回复。")
        await self.hooks.reply(message, "\n".join(lines), command_reply=True, command_name="/compact")
        return True

    def _can_use_top_level_session_command(self, message: IncomingMessage) -> bool:
        return self.session_scope.is_top_level_p2p_command(message) or self.session_scope.is_card_action_message(message)

    def _can_use_top_level_workspace_command(self, message: IncomingMessage) -> bool:
        if self.session_scope.is_top_level_p2p_command(message):
            return True
        return self.session_scope.is_card_action_message(message) and not message.root_id and not message.thread_id

    def _top_level_thread_scope_key(self, message: IncomingMessage) -> str:
        return self.session_scope.top_level_thread_scope_key(message)

    async def _list_runtime_sessions(self, session: SessionRecord, limit: int) -> list[RuntimeSessionSummary]:
        assert self.runtime_service is not None
        rows, _cursor = await self.runtime_service.list_sessions(
            session.backend,
            ListSessionsRequest(limit=limit, cwd=session.cwd),
        )
        return [
            RuntimeSessionSummary(
                session_id=row.native_session_id,
                preview=row.preview,
                cwd=row.cwd,
                updated_at=row.updated_at,
                status=row.status,
                name=row.title,
            )
            for row in rows
        ]

    async def _read_runtime_session(self, session: SessionRecord, session_id: str) -> RuntimeSessionDetails:
        assert self.runtime_service is not None
        transcript = await self.runtime_service.read_session(
            SessionLocator(backend=session.backend, native_session_id=session_id)  # type: ignore[arg-type]
        )
        return RuntimeSessionDetails(
            session_id=transcript.summary.native_session_id,
            preview=transcript.summary.preview,
            cwd=transcript.summary.cwd,
            updated_at=transcript.summary.updated_at,
            status=transcript.summary.status,
            name=transcript.summary.title,
            messages=tuple(
                RuntimeTranscriptMessage(role=item.role, text=item.text)
                for item in transcript.messages
                if item.text.strip()
            ),
        )

    async def _compact_runtime_session(self, session: SessionRecord, session_id: str) -> dict[str, object]:
        assert self.runtime_service is not None
        return await self.runtime_service.compact_locator(
            SessionLocator(backend=session.backend, native_session_id=session_id)  # type: ignore[arg-type]
        )

    def _supports_runtime_session_listing(self, session: SessionRecord) -> bool:
        if self.runtime_service is None:
            return False
        backend = self.runtime_service.backends.get(session.backend)
        return backend is not None and backend.capabilities().supports_session_list

    def _supports_runtime_compact(self, session: SessionRecord) -> bool:
        if self.runtime_service is None:
            return False
        backend = self.runtime_service.backends.get(session.backend)
        return backend is not None and backend.capabilities().supports_compact

    async def _resolve_resume_session_id(
        self,
        session_key: str,
        session: SessionRecord,
        target: str,
        page: int,
    ) -> str:
        normalized = target.strip()
        if not normalized:
            return ""
        sessions = await self._list_runtime_sessions(session, max(DEFAULT_SESSION_LIST_PAGE_SIZE * max(page, 1), 20))
        lowered = normalized.lower()
        if lowered in {"latest", "prev", "previous"}:
            return sessions[0].session_id if sessions else ""
        if normalized.isdigit():
            index = int(normalized) - 1
            if 0 <= index < len(sessions):
                return sessions[index].session_id
        for runtime_session in sessions:
            if normalized == runtime_session.session_id:
                return runtime_session.session_id
        local_match = self.session_browser.find_local_session(session_key, normalized)
        if local_match is not None:
            return local_match.native_session_id or ""
        return ""

    def _format_runtime_session_resume_success(self, session: SessionRecord, runtime_session: RuntimeSessionDetails) -> str:
        title = runtime_session.name or runtime_session.preview or runtime_session.session_id
        lines = [
            f"已连接 {session.backend} 会话：{title}",
            f"session_id={runtime_session.session_id}",
            f"cwd={self._format_full_cwd(runtime_session.cwd or session.cwd)}",
        ]
        updated_at = self._format_user_facing_time(runtime_session.updated_at)
        if updated_at:
            lines.append(f"最近更新：{updated_at}")
        if runtime_session.status:
            lines.append(f"status={runtime_session.status}")
        if runtime_session.preview:
            lines.extend(["", f"预览：{self.session_presentation.shorten(runtime_session.preview, 120)}"])
        lines.extend(["", "已在当前顶层对话中连接；接下来直接继续发消息即可。"])
        return "\n".join(lines)

    def _format_user_facing_time(self, value: str) -> str:
        raw = value.strip()
        if not raw:
            return ""
        if raw.isdigit():
            timestamp = int(raw)
            if timestamp > 10**12:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return raw
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%Y-%m-%d %H:%M:%S")

    def _format_full_cwd(self, cwd: str) -> str:
        raw = cwd.strip()
        if not raw:
            return ""
        path = Path(raw).expanduser()
        home = Path.home()
        try:
            relative = path.relative_to(home)
        except ValueError:
            return str(path)
        return "~" if str(relative) == "." else f"~/{relative}"

    def _parse_resume_command_args(self, arg_text: str) -> ResumeCommandArgs:
        args = self._parse_paging_command_args(arg_text)
        if args.target.lower() == "list":
            raise ValueError("`list` 已移除；直接使用 /resume")
        return ResumeCommandArgs(target=args.target, page=args.page, sort_mode=args.sort_mode)

    def _parse_panel_command_args(self, arg_text: str) -> PanelCommandArgs:
        args = self._parse_paging_command_args(arg_text)
        uses_session_paging = args.page != 1 or args.sort_mode != DEFAULT_SESSION_LIST_SORT
        view = self._normalize_panel_view(args.target or ("sessions" if uses_session_paging else "home"))
        if view not in {"sessions", "workspace"} and uses_session_paging:
            raise ValueError("只有 workspace 视图支持分页参数")
        if view == "workspace" and args.sort_mode != DEFAULT_SESSION_LIST_SORT:
            raise ValueError("工作区视图不支持 --sort")
        if view != "workspace" and (args.target_path or args.query):
            raise ValueError("只有 workspace 视图支持 --path 和 --query")
        return PanelCommandArgs(view=view, page=args.page, sort_mode=args.sort_mode, target_path=args.target_path, query=args.query)

    def _parse_paging_command_args(self, arg_text: str) -> PagingCommandArgs:
        tokens = shlex.split(arg_text) if arg_text else []
        target = ""
        page = 1
        sort_mode = DEFAULT_SESSION_LIST_SORT
        target_path = ""
        query = ""
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
            elif token == "--path":
                index += 1
                if index >= len(tokens):
                    raise ValueError("--path 缺少目录")
                target_path = tokens[index]
            elif token.startswith("--path="):
                target_path = token.split("=", 1)[1]
            elif token == "--query":
                index += 1
                if index >= len(tokens):
                    raise ValueError("--query 缺少搜索词")
                query = tokens[index]
            elif token.startswith("--query="):
                query = token.split("=", 1)[1]
            elif token.startswith("--"):
                raise ValueError(f"不支持的选项：{token}")
            elif not target:
                target = token
            else:
                raise ValueError(f"多余参数：{token}")
            index += 1
        return PagingCommandArgs(target=target, page=page, sort_mode=sort_mode, target_path=target_path, query=query)

    def _normalize_panel_view(self, value: str) -> PanelView:
        aliases: dict[str, PanelView] = {
            "": "home",
            "home": "home",
            "overview": "home",
            "main": "home",
            "session": "sessions",
            "sessions": "sessions",
            "list": "sessions",
            "workspace": "workspace",
            "workspaces": "workspace",
            "directory": "workspace",
            "directories": "workspace",
            "dir": "workspace",
            "dirs": "workspace",
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
                        f"channel={format_release_channel(target_channel)}",
                        f"cwd={self.session_presentation.format_cwd(result.session.cwd, result.session)}",
                        f"sandbox={result.session.safety_mode}",
                        f"reason={reason}" if reason else "",
                        "已中断上一条进行中的回复。" if result.cancelled_active_run else "",
                        "已写入切换记录，后续智能体可据此继续修复。",
                    ],
                )
            ),
            command_reply=True,
        )

    async def _handle_workspace(self, message: IncomingMessage, session_key: str, session: SessionRecord, arg_text: str) -> bool:
        if not self._can_use_top_level_workspace_command(message):
            await self.hooks.reply(message, "`/workspace` 只允许在私聊顶层使用；子 thread 不应改工作区。", command_reply=True, command_name="/workspace")
            return True
        tokens = shlex.split(arg_text) if arg_text else []
        if not tokens or tokens[0] in {"list", "search"} or tokens[0].startswith("--"):
            try:
                remainder = arg_text if (not tokens or tokens[0].startswith("--")) else " ".join(tokens[1:])
                args = self._parse_panel_command_args(f"workspace {remainder}".strip())
            except ValueError as exc:
                await self.hooks.reply(message, f"workspace 参数无效：{exc}", command_reply=True, command_name="/workspace")
                return True
            await self.hooks.send_panel(message, session_key, session, args)
            return True
        if tokens[0] == "open":
            if len(tokens) < 2:
                await self.hooks.reply(message, "workspace 参数无效：open 需要目录路径", command_reply=True, command_name="/workspace")
                return True
            try:
                path = self.workspace.resolve_workspace_selection(tokens[1], session)
            except ValueError as exc:
                await self.hooks.reply(message, f"workspace 参数无效：{exc}", command_reply=True, command_name="/workspace")
                return True
            extra_query = ""
            if len(tokens) > 2:
                extra_query = " ".join(tokens[2:])
            remainder = f"workspace --path {shlex.quote(str(path))} {extra_query}".strip()
            try:
                args = self._parse_panel_command_args(remainder)
            except ValueError as exc:
                await self.hooks.reply(message, f"workspace 参数无效：{exc}", command_reply=True, command_name="/workspace")
                return True
            await self.hooks.send_panel(message, session_key, session, args)
            return True
        if tokens[0] == "select":
            if len(tokens) < 2:
                await self.hooks.reply(message, "workspace 参数无效：select 需要目录路径", command_reply=True, command_name="/workspace")
                return True
            return await self._switch_workspace_directory(message, session_key, session, tokens[1], command_name="/workspace")
        await self.hooks.reply(message, "workspace 参数无效：只支持 /workspace、/workspace --page N [--path <dir>] [--query <text>]、/workspace open <path>、/workspace select <path>", command_reply=True, command_name="/workspace")
        return True

    async def _switch_workspace_directory(
        self,
        message: IncomingMessage,
        session_key: str,
        session: SessionRecord,
        raw_path: str,
        *,
        command_name: str,
    ) -> bool:
        try:
            next_cwd = self.workspace.resolve_workspace_selection(raw_path, session)
        except ValueError as exc:
            await self.hooks.reply(message, f"工作区切换失败：{exc}", command_reply=True, command_name=command_name)
            return True
        next_session = self.session_mutations.switch_cwd(session_key, session, next_cwd)
        await self.hooks.reply(
            message,
            "\n".join([
                f"工作区已切换到 {self.workspace.format_cwd(next_session.cwd, next_session)}。",
                "现在直接发消息，就会在这个目录进入 Codex。",
                "当前 scope 已原地更新；如需切回旧 thread，请用 /resume。",
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
        if backend not in available:
            await self.hooks.reply(message, f"backend 仅支持：{', '.join(available)}", command_reply=True)
            return True
        next_session = self.session_mutations.switch_backend(session_key, session, backend)
        await self.hooks.reply(message, f"backend 已切换到 {backend}；当前 scope 会从下一条真实消息开始使用新 thread。", command_reply=True)
        return True

    async def _handle_shortcut(self, message: IncomingMessage, session_key: str, session: SessionRecord, arg_text: str) -> bool:
        tokens = shlex.split(arg_text) if arg_text else []
        action = tokens[0].lower() if tokens else "list"

        if action in {"list", "ls"}:
            shortcut_entries = self.shortcuts.build_directory_shortcut_entries(session, limit=100)
            if not shortcut_entries:
                await self.hooks.reply(
                    message,
                    "当前没有可用的快捷目录。\n\n先用 `/shortcut add <name> <path>` 新增一个，或直接打开 `/workspace`。",
                    command_reply=True,
                    command_name="/shortcut",
                )
                return True
            lines = ["快捷目录："]
            for entry in shortcut_entries:
                lines.append(f"- {entry['label']} -> {entry['display_path']} [{entry['channels']}]")
            lines.extend(["", "快速切换：/shortcut use <name>"])
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
                        f"使用 `/shortcut use {shortcut.name}` 或 `/workspace`。",
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
            target = self.shortcuts.resolve_directory_shortcut(name, session)
            if target is None:
                await self.hooks.reply(
                    message,
                    f"没有找到当前通道可用的快捷目录：`{name}`。\n先发 `/shortcut list` 看可用入口。",
                    command_reply=True,
                    command_name="/shortcut",
                )
                return True
            return await self._switch_workspace_directory(message, session_key, session, str(target), command_name="/shortcut")

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
