from __future__ import annotations

from openrelay.session import SessionScopeResolver

from ..command_context import CommandContext, ResumeCommandArgs, RuntimeCommandHooks
from ..command_services.runtime_session_commands import RuntimeSessionCommandService

RESUME_USAGE = "使用 /resume 打开后端会话卡片，或 /resume [latest|<序号>|<session_id>|<local_session_id>] 直接连接。"


class RuntimeSessionCommandHandler:
    def __init__(
        self,
        hooks: RuntimeCommandHooks,
        session_scope: SessionScopeResolver,
        service: RuntimeSessionCommandService,
        parse_paging_command_args,
    ) -> None:
        self.hooks = hooks
        self.session_scope = session_scope
        self.service = service
        self.parse_paging_command_args = parse_paging_command_args

    async def handle(self, ctx: CommandContext) -> bool:
        if ctx.command.name == "/resume":
            return await self._handle_resume(ctx)
        if ctx.command.name == "/compact":
            return await self._handle_compact(ctx)
        return False

    async def _handle_resume(self, ctx: CommandContext) -> bool:
        if not self._can_use_top_level_session_command(ctx.message):
            await self.hooks.reply(ctx.message, "`/resume` 只允许在私聊顶层使用；子 thread 会固定绑定当前后端会话。", command_reply=True, command_name="/resume")
            return True
        try:
            args = self._parse_resume_command_args(ctx.command.arg_text)
        except ValueError as exc:
            await self.hooks.reply(ctx.message, f"resume 参数无效：{exc}\n{RESUME_USAGE}", command_reply=True, command_name="/resume")
            return True
        scope_key = self.session_scope.top_level_thread_scope_key(ctx.message)
        if not self.service.supports_session_listing(ctx.session):
            await self.hooks.reply(ctx.message, "当前后端不支持 `/resume` 原生命令。", command_reply=True, command_name="/resume")
            return True
        if not args.target:
            await self.hooks.send_session_list(ctx.message, ctx.session_key, ctx.session, args.page, args.sort_mode)
            return True
        target_session_id = await self.service.resolve_resume_session_id(ctx.session_key, ctx.session, args.target, args.page)
        if not target_session_id:
            await self.hooks.reply(ctx.message, "没有找到可连接的后端会话。先发 `/resume` 查看可用会话。", command_reply=True, command_name="/resume")
            return True
        runtime_session = await self.service.read_runtime_session(ctx.session, target_session_id)
        resumed_session = self.service.bind_native_thread(scope_key, ctx.session, runtime_session)
        await self.hooks.reply(
            ctx.message,
            self.service.format_runtime_session_resume_success(resumed_session, runtime_session),
            command_reply=True,
            command_name="/resume",
        )
        return True

    async def _handle_compact(self, ctx: CommandContext) -> bool:
        if not self.service.supports_compact(ctx.session):
            await self.hooks.reply(ctx.message, "当前后端不支持 `/compact` 原生命令。", command_reply=True, command_name="/compact")
            return True
        cancelled_active_run = await self.hooks.cancel_active_run_for_session(ctx.session, "/compact")
        target = ctx.command.arg_text.strip()
        session_id = ctx.session.native_session_id
        if target:
            session_id = await self.service.resolve_resume_session_id(ctx.session_key, ctx.session, target, page=1)
        if not session_id:
            await self.hooks.reply(ctx.message, "当前没有可 compact 的后端会话。先恢复一个会话，或先发一条真实消息创建会话。", command_reply=True, command_name="/compact")
            return True
        result = await self.service.compact_runtime_session(ctx.session, session_id)
        compact_id = str(result.get("compactId") or result.get("id") or "").strip()
        lines = [f"{ctx.session.backend} compact 已完成：{session_id}"]
        if compact_id:
            lines.append(f"compact_id={compact_id}")
        if cancelled_active_run:
            lines.append("已先中断上一条进行中的回复。")
        await self.hooks.reply(ctx.message, "\n".join(lines), command_reply=True, command_name="/compact")
        return True

    def _can_use_top_level_session_command(self, message) -> bool:
        return self.session_scope.is_top_level_p2p_command(message) or self.session_scope.is_card_action_message(message)

    def _parse_resume_command_args(self, arg_text: str) -> ResumeCommandArgs:
        args = self.parse_paging_command_args(arg_text)
        if args.target.lower() == "list":
            raise ValueError("`list` 已移除；直接使用 /resume")
        return ResumeCommandArgs(target=args.target, page=args.page, sort_mode=args.sort_mode)
