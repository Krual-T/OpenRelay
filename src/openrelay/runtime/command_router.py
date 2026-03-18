from __future__ import annotations

import shlex

from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.core import AppConfig, IncomingMessage, SessionRecord
from openrelay.presentation.runtime_status import RuntimeStatusPresenter
from openrelay.presentation.session import SessionPresentation
from openrelay.release import ReleaseCommandService
from openrelay.session import DEFAULT_SESSION_LIST_SORT, SessionBrowser, SessionMutationService, SessionScopeResolver, SessionShortcutService, SessionWorkspaceService
from openrelay.storage import StateStore

from .command_context import CommandContext, PanelCommandArgs, PagingCommandArgs, RuntimeCommandHooks
from .command_handlers.control import ControlCommandHandler
from .command_handlers.release import ReleaseCommandHandler
from .command_handlers.runtime_session import RuntimeSessionCommandHandler
from .command_handlers.session_config import SessionConfigCommandHandler
from .command_handlers.shortcut import ShortcutCommandHandler
from .command_handlers.workspace import WorkspaceCommandHandler
from .command_parser import CommandParser
from .command_registry import CommandRegistry, CommandSpec
from .command_services.runtime_session_commands import RuntimeSessionCommandService
from .command_services.session_commands import SessionCommandService
from .command_services.workspace_commands import WorkspaceCommandService
from .help import HelpRenderer


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
        self.parser = CommandParser()
        self.registry = self._build_registry()

    async def handle(self, message: IncomingMessage, session_key: str, session: SessionRecord) -> bool:
        command = self.parser.parse(message.text)
        if command is None:
            return False
        spec = self.registry.spec_for(command.name)
        if spec is not None and spec.requires_admin and not self.hooks.is_admin(message.sender_open_id):
            await self.hooks.reply(message, "这个命令只允许管理员使用。", command_reply=True)
            return True
        handler = self.registry.resolve(command.name)
        if handler is None:
            await self.hooks.reply(message, f"本地命令未实现：{command.name}。发送 /help 查看可用命令。", command_reply=True)
            return True
        return await handler.handle(CommandContext(message=message, session_key=session_key, session=session, command=command))

    def _build_registry(self) -> CommandRegistry:
        registry = CommandRegistry()
        session_service = SessionCommandService(self.session_mutations, self.session_presentation)
        workspace_service = WorkspaceCommandService(self.workspace, self.shortcuts, self.session_mutations)
        runtime_session_service = RuntimeSessionCommandService(
            self.runtime_service,
            self.session_browser,
            self.session_mutations,
            self.session_presentation,
        )
        control_handler = ControlCommandHandler(self.hooks, self.status_presenter)
        session_config_handler = SessionConfigCommandHandler(self.hooks, session_service)
        release_handler = ReleaseCommandHandler(self.hooks, self.release_commands, self.session_presentation)
        runtime_session_handler = RuntimeSessionCommandHandler(
            self.hooks,
            self.session_scope,
            runtime_session_service,
            self._parse_paging_command_args,
        )
        workspace_handler = WorkspaceCommandHandler(
            self.hooks,
            self.session_scope,
            workspace_service,
            self._parse_panel_command_args,
        )
        shortcut_handler = ShortcutCommandHandler(self.hooks, workspace_service)
        for spec in [
            CommandSpec("/ping"),
            CommandSpec("/help", aliases=("/tools",)),
            CommandSpec("/panel"),
            CommandSpec("/restart", requires_admin=True),
            CommandSpec("/status"),
            CommandSpec("/usage"),
            CommandSpec("/stop"),
        ]:
            registry.register(spec, control_handler)
        for spec in [
            CommandSpec("/clear"),
            CommandSpec("/reset"),
            CommandSpec("/model"),
            CommandSpec("/sandbox", aliases=("/mode",)),
            CommandSpec("/backend"),
        ]:
            registry.register(spec, session_config_handler)
        for spec in [CommandSpec("/main"), CommandSpec("/stable"), CommandSpec("/develop")]:
            registry.register(spec, release_handler)
        for spec in [CommandSpec("/resume"), CommandSpec("/compact")]:
            registry.register(spec, runtime_session_handler)
        registry.register(CommandSpec("/workspace", aliases=("/ws",)), workspace_handler)
        registry.register(CommandSpec("/shortcut", aliases=("/shortcuts",)), shortcut_handler)
        return registry

    def _parse_panel_command_args(self, arg_text: str) -> PanelCommandArgs:
        args = self._parse_paging_command_args(arg_text)
        uses_session_paging = args.page != 1 or args.sort_mode != DEFAULT_SESSION_LIST_SORT
        view = self._normalize_panel_view(args.target or ("sessions" if uses_session_paging else "home"))
        if view not in {"sessions", "workspace"} and uses_session_paging:
            raise ValueError("只有 workspace 视图支持分页参数")
        if view == "workspace" and args.sort_mode != DEFAULT_SESSION_LIST_SORT:
            raise ValueError("工作区视图不支持 --sort")
        if view != "workspace" and (args.target_path or args.query or args.show_hidden):
            raise ValueError("只有 workspace 视图支持 --path、--query 和 --hidden")
        return PanelCommandArgs(
            view=view,
            page=args.page,
            sort_mode=args.sort_mode,
            target_path=args.target_path,
            query=args.query,
            show_hidden=args.show_hidden,
        )

    def _parse_paging_command_args(self, arg_text: str) -> PagingCommandArgs:
        tokens = shlex.split(arg_text) if arg_text else []
        target = ""
        page = 1
        sort_mode = DEFAULT_SESSION_LIST_SORT
        target_path = ""
        query = ""
        show_hidden = False
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
            elif token in {"--hidden", "--all"}:
                show_hidden = True
            elif token.startswith("--"):
                raise ValueError(f"不支持的选项：{token}")
            elif not target:
                target = token
            else:
                raise ValueError(f"多余参数：{token}")
            index += 1
        return PagingCommandArgs(target=target, page=page, sort_mode=sort_mode, target_path=target_path, query=query, show_hidden=show_hidden)

    def _normalize_panel_view(self, value: str):
        aliases = {
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
