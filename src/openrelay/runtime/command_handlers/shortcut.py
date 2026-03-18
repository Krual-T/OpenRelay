from __future__ import annotations

import shlex

from ..command_context import CommandContext, RuntimeCommandHooks
from ..command_services.workspace_commands import WorkspaceCommandService

SHORTCUT_USAGE = (
    "使用 /shortcut list | /shortcut add <name> <path> [all|main|develop] | "
    "/shortcut remove <name> | /shortcut use <name>。"
)


class ShortcutCommandHandler:
    def __init__(self, hooks: RuntimeCommandHooks, service: WorkspaceCommandService) -> None:
        self.hooks = hooks
        self.service = service

    async def handle(self, ctx: CommandContext) -> bool:
        if ctx.command.name not in {"/shortcut", "/shortcuts"}:
            return False
        tokens = shlex.split(ctx.command.arg_text) if ctx.command.arg_text else []
        action = tokens[0].lower() if tokens else "list"
        if action in {"list", "ls"}:
            shortcut_entries = self.service.build_directory_shortcut_entries(ctx.session, limit=100)
            if not shortcut_entries:
                await self.hooks.reply(
                    ctx.message,
                    "当前没有可用的快捷目录。\n\n先用 `/shortcut add <name> <path>` 新增一个，或直接打开 `/workspace`。",
                    command_reply=True,
                    command_name="/shortcut",
                )
                return True
            lines = ["快捷目录："]
            for entry in shortcut_entries:
                lines.append(f"- {entry['label']} -> {entry['display_path']} [{entry['channels']}]")
            lines.extend(["", "快速切换：/shortcut use <name>"])
            await self.hooks.reply(ctx.message, "\n".join(lines), command_reply=True, command_name="/shortcut")
            return True
        if action == "add":
            try:
                shortcut = self.service.parse_shortcut_add(tokens[1:])
            except ValueError as exc:
                await self.hooks.reply(ctx.message, f"shortcut 参数无效：{exc}\n{SHORTCUT_USAGE}", command_reply=True, command_name="/shortcut")
                return True
            self.service.save_directory_shortcut(shortcut)
            await self.hooks.reply(
                ctx.message,
                "\n".join([
                    f"已保存快捷目录 `{shortcut.name}`。",
                    f"path={shortcut.path}",
                    f"channels={','.join(shortcut.channels)}",
                    f"使用 `/shortcut use {shortcut.name}` 或 `/workspace`。",
                ]),
                command_reply=True,
                command_name="/shortcut",
            )
            return True
        if action in {"remove", "rm", "del", "delete"}:
            name = tokens[1].strip() if len(tokens) > 1 else ""
            if not name:
                await self.hooks.reply(ctx.message, f"shortcut 参数无效：缺少名称\n{SHORTCUT_USAGE}", command_reply=True, command_name="/shortcut")
                return True
            removed = self.service.remove_directory_shortcut(name)
            if removed:
                await self.hooks.reply(ctx.message, f"已删除快捷目录 `{name}`。", command_reply=True, command_name="/shortcut")
                return True
            await self.hooks.reply(ctx.message, f"没有找到可删除的快捷目录：`{name}`。", command_reply=True, command_name="/shortcut")
            return True
        if action in {"cd", "go", "use"}:
            name = tokens[1].strip() if len(tokens) > 1 else ""
            if not name:
                await self.hooks.reply(ctx.message, f"shortcut 参数无效：缺少名称\n{SHORTCUT_USAGE}", command_reply=True, command_name="/shortcut")
                return True
            target = self.service.resolve_directory_shortcut(name, ctx.session)
            if target is None:
                await self.hooks.reply(
                    ctx.message,
                    f"没有找到当前通道可用的快捷目录：`{name}`。\n先发 `/shortcut list` 看可用入口。",
                    command_reply=True,
                    command_name="/shortcut",
                )
                return True
            try:
                next_session = self.service.switch_workspace_directory(ctx.session_key, ctx.session, str(target))
            except ValueError as exc:
                await self.hooks.reply(ctx.message, f"工作区切换失败：{exc}", command_reply=True, command_name="/shortcut")
                return True
            await self.hooks.reply(
                ctx.message,
                self.service.format_workspace_switch_success(next_session),
                command_reply=True,
                command_name="/shortcut",
            )
            return True
        await self.hooks.reply(ctx.message, f"shortcut 参数无效：不支持的动作 `{action}`\n{SHORTCUT_USAGE}", command_reply=True, command_name="/shortcut")
        return True
