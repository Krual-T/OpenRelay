from __future__ import annotations

from ..command_context import CommandContext, RuntimeCommandHooks
from ..command_services.session_commands import SessionCommandService


class SessionConfigCommandHandler:
    def __init__(self, hooks: RuntimeCommandHooks, service: SessionCommandService) -> None:
        self.hooks = hooks
        self.service = service

    async def handle(self, ctx: CommandContext) -> bool:
        name = ctx.command.name
        arg_text = ctx.command.arg_text
        if name == "/clear":
            self.service.clear_context(ctx.session_key, ctx.session)
            await self.hooks.reply(ctx.message, "已清空当前上下文；当前 scope 保留原目录和配置。", command_reply=True)
            return True
        if name == "/reset":
            self.service.reset_scope(ctx.session_key)
            await self.hooks.reply(ctx.message, "会话已重置。", command_reply=True)
            return True
        if name == "/model":
            if not arg_text:
                await self.hooks.reply(ctx.message, self.service.current_model_text(ctx.session), command_reply=True)
                return True
            next_session = self.service.switch_model(ctx.session_key, ctx.session, arg_text)
            await self.hooks.reply(
                ctx.message,
                f"model 已切换到 {self.service.session_presentation.effective_model(next_session)}；当前 scope 会从下一条真实消息开始使用新 thread。",
                command_reply=True,
            )
            return True
        if name in {"/sandbox", "/mode"}:
            if not arg_text:
                await self.hooks.reply(ctx.message, self.service.current_sandbox_text(ctx.session), command_reply=True)
                return True
            mode = arg_text.lower()
            if not self.service.validate_sandbox_mode(mode):
                await self.hooks.reply(ctx.message, "sandbox 仅支持：read-only / workspace-write / danger-full-access", command_reply=True)
                return True
            if mode == "danger-full-access" and not self.hooks.is_admin(ctx.message.sender_open_id):
                await self.hooks.reply(ctx.message, "danger-full-access 只允许管理员切换。", command_reply=True)
                return True
            next_session = self.service.switch_sandbox(ctx.session_key, ctx.session, mode)
            await self.hooks.reply(
                ctx.message,
                f"sandbox 已切换到 {next_session.safety_mode}；当前 scope 会从下一条真实消息开始使用新 thread。",
                command_reply=True,
            )
            return True
        if name == "/backend":
            available = self.hooks.available_backend_names()
            if not arg_text or arg_text.lower() == "list":
                await self.hooks.reply(
                    ctx.message,
                    "\n".join([f"backend={ctx.session.backend}", f"available={', '.join(available)}"]),
                    command_reply=True,
                )
                return True
            backend = arg_text.lower()
            if backend not in available:
                await self.hooks.reply(ctx.message, f"backend 仅支持：{', '.join(available)}", command_reply=True)
                return True
            self.service.switch_backend(ctx.session_key, ctx.session, backend)
            await self.hooks.reply(ctx.message, f"backend 已切换到 {backend}；当前 scope 会从下一条真实消息开始使用新 thread。", command_reply=True)
            return True
        return False
