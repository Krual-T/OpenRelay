from __future__ import annotations

import shlex

from openrelay.session import SessionScopeResolver

from ..command_context import CommandContext, RuntimeCommandHooks
from ..command_services.workspace_commands import WorkspaceCommandService


class WorkspaceCommandHandler:
    def __init__(
        self,
        hooks: RuntimeCommandHooks,
        session_scope: SessionScopeResolver,
        service: WorkspaceCommandService,
        parse_panel_command_args,
    ) -> None:
        self.hooks = hooks
        self.session_scope = session_scope
        self.service = service
        self.parse_panel_command_args = parse_panel_command_args

    async def handle(self, ctx: CommandContext) -> bool:
        if ctx.command.name not in {"/workspace", "/ws"}:
            return False
        if not self._can_use_top_level_workspace_command(ctx.message):
            await self.hooks.reply(ctx.message, "`/workspace` 只允许在私聊顶层使用；子 thread 不应改工作区。", command_reply=True, command_name="/workspace")
            return True
        tokens = shlex.split(ctx.command.arg_text) if ctx.command.arg_text else []
        if not tokens or tokens[0] in {"list", "search"} or tokens[0].startswith("--"):
            try:
                remainder = ctx.command.arg_text if (not tokens or tokens[0].startswith("--")) else " ".join(tokens[1:])
                args = self.parse_panel_command_args(f"workspace {remainder}".strip())
            except ValueError as exc:
                await self.hooks.reply(ctx.message, f"workspace 参数无效：{exc}", command_reply=True, command_name="/workspace")
                return True
            await self.hooks.send_panel(ctx.message, ctx.session_key, ctx.session, args)
            return True
        if tokens[0] == "open":
            if len(tokens) < 2:
                await self.hooks.reply(ctx.message, "workspace 参数无效：open 需要目录路径", command_reply=True, command_name="/workspace")
                return True
            try:
                path = self.service.resolve_workspace_browser_path(tokens[1], ctx.session)
            except ValueError as exc:
                await self.hooks.reply(ctx.message, f"workspace 参数无效：{exc}", command_reply=True, command_name="/workspace")
                return True
            extra_query = " ".join(tokens[2:]) if len(tokens) > 2 else ""
            remainder = f"workspace --path {shlex.quote(str(path))} {extra_query}".strip()
            try:
                args = self.parse_panel_command_args(remainder)
            except ValueError as exc:
                await self.hooks.reply(ctx.message, f"workspace 参数无效：{exc}", command_reply=True, command_name="/workspace")
                return True
            await self.hooks.send_panel(ctx.message, ctx.session_key, ctx.session, args)
            return True
        if tokens[0] == "select":
            if len(tokens) < 2:
                await self.hooks.reply(ctx.message, "workspace 参数无效：select 需要目录路径", command_reply=True, command_name="/workspace")
                return True
            return await self._switch_workspace_directory(ctx, tokens[1], command_name="/workspace")
        await self.hooks.reply(ctx.message, "workspace 参数无效：只支持 /workspace、/workspace --page N [--path <dir>] [--query <text>] [--hidden]、/workspace open <path>、/workspace select <path>", command_reply=True, command_name="/workspace")
        return True

    async def _switch_workspace_directory(self, ctx: CommandContext, raw_path: str, *, command_name: str) -> bool:
        try:
            next_session = self.service.switch_workspace_directory(ctx.session_key, ctx.session, raw_path)
        except ValueError as exc:
            await self.hooks.reply(ctx.message, f"工作区切换失败：{exc}", command_reply=True, command_name=command_name)
            return True
        await self.hooks.reply(
            ctx.message,
            self.service.format_workspace_switch_success(next_session),
            command_reply=True,
            command_name=command_name,
        )
        return True

    def _can_use_top_level_workspace_command(self, message) -> bool:
        if self.session_scope.is_top_level_p2p_command(message):
            return True
        return self.session_scope.is_card_action_message(message) and not message.root_id and not message.thread_id
