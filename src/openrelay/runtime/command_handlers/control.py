from __future__ import annotations

from openrelay.presentation.runtime_status import RuntimeStatusPresenter

from ..command_context import CommandContext, RuntimeCommandHooks


class ControlCommandHandler:
    def __init__(self, hooks: RuntimeCommandHooks, status_presenter: RuntimeStatusPresenter) -> None:
        self.hooks = hooks
        self.status_presenter = status_presenter

    async def handle(self, ctx: CommandContext) -> bool:
        name = ctx.command.name
        if name == "/ping":
            await self.hooks.reply(ctx.message, "pong", command_reply=True)
            return True
        if name in {"/help", "/tools"}:
            await self.hooks.send_help(ctx.message, ctx.session_key, ctx.session, self.hooks.available_backend_names())
            return True
        if name == "/panel":
            await self.hooks.reply(
                ctx.message,
                "`/panel` 已移除；恢复历史会话请用 `/resume`，切工作区请用 `/workspace`，查看现场请用 `/status`。",
                command_reply=True,
                command_name="/panel",
            )
            return True
        if name == "/restart":
            await self.hooks.reply(ctx.message, "正在重启 openrelay，预计几秒后恢复。", command_reply=True)
            self.hooks.schedule_restart()
            return True
        if name in {"/status", "/usage"}:
            await self.hooks.reply(
                ctx.message,
                self.status_presenter.build_text(name, ctx.session_key, ctx.session),
                command_reply=True,
                command_name=name,
            )
            return True
        if name == "/stop":
            await self.hooks.stop(ctx.message, ctx.session_key)
            return True
        return False
