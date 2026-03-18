from __future__ import annotations

from openrelay.core import format_release_channel
from openrelay.presentation.session import SessionPresentation
from openrelay.release import ReleaseCommandService

from ..command_context import CommandContext, RuntimeCommandHooks


class ReleaseCommandHandler:
    def __init__(
        self,
        hooks: RuntimeCommandHooks,
        release_commands: ReleaseCommandService,
        session_presentation: SessionPresentation,
    ) -> None:
        self.hooks = hooks
        self.release_commands = release_commands
        self.session_presentation = session_presentation

    async def handle(self, ctx: CommandContext) -> bool:
        if ctx.command.name not in {"/main", "/stable", "/develop"}:
            return False
        target_channel = "develop" if ctx.command.name == "/develop" else "main"
        cancelled_active_run = await self.hooks.cancel_active_run_for_session(ctx.session, ctx.command.name)
        try:
            result = self.release_commands.switch_channel(
                session_key=ctx.session_key,
                session=ctx.session,
                target_channel=target_channel,
                command_name=ctx.command.name,
                reason=ctx.command.arg_text,
                chat_id=ctx.message.chat_id,
                operator_open_id=ctx.message.sender_open_id,
                cancelled_active_run=cancelled_active_run,
            )
        except FileNotFoundError as exc:
            await self.hooks.reply(ctx.message, str(exc), command_reply=True)
            return True
        await self.hooks.reply(
            ctx.message,
            "\n".join(
                filter(
                    None,
                    [
                        "已强制切到 main 稳定版本。" if target_channel == "main" else "已切到 develop 修复版本。",
                        f"channel={format_release_channel(target_channel)}",
                        f"cwd={self.session_presentation.format_cwd(result.session.cwd, result.session)}",
                        f"sandbox={result.session.safety_mode}",
                        f"reason={ctx.command.arg_text}" if ctx.command.arg_text else "",
                        "已中断上一条进行中的回复。" if result.cancelled_active_run else "",
                        "已写入切换记录，后续智能体可据此继续修复。",
                    ],
                )
            ),
            command_reply=True,
        )
        return True
