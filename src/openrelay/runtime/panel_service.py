from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from openrelay.backends import BackendDescriptor
from openrelay.core import AppConfig, IncomingMessage, SessionRecord, format_release_channel, infer_release_channel
from openrelay.feishu import FeishuMessenger
from openrelay.session import (
    SessionBrowser,
    SessionShortcutService,
    SessionSortMode,
    SessionUX,
    SessionWorkspaceService,
    build_session_list_card,
)

from .commands import PanelCommandArgs
from .panel import build_panel_card
from .replying import RuntimeReplyPolicy


FallbackReply = Callable[[IncomingMessage, str, str], Awaitable[None]]


@dataclass(slots=True)
class RuntimePanelService:
    config: AppConfig
    messenger: FeishuMessenger
    backend_descriptors: dict[str, BackendDescriptor]
    session_browser: SessionBrowser
    session_ux: SessionUX
    workspace: SessionWorkspaceService
    shortcuts: SessionShortcutService
    reply_policy: RuntimeReplyPolicy
    reply_fallback: FallbackReply

    async def send_panel(self, message: IncomingMessage, session_key: str, session: SessionRecord, args: PanelCommandArgs) -> None:
        panel_info = self._build_panel_base_info(message, session_key, session, args.view)
        fallback_text = ""
        if args.view == "sessions":
            session_page = self.session_browser.list_page(session_key, session, page=args.page, sort_mode=args.sort_mode)
            card = build_panel_card(
                {
                    **panel_info,
                    "page": session_page.page,
                    "total_pages": session_page.total_pages,
                    "sort_mode": session_page.sort_mode,
                    "sessions": self.session_ux.build_session_display_entries(session_page.entries, start_index=session_page.start_index),
                }
            )
            fallback_text = self._build_panel_sessions_text(session_page)
        elif args.view == "directories":
            directory_shortcuts = self.shortcuts.build_directory_shortcut_entries(session)
            card = build_panel_card({**panel_info, "directory_shortcuts": directory_shortcuts})
            fallback_text = self._build_panel_directories_text(directory_shortcuts)
        elif args.view == "commands":
            command_entries = self._build_panel_command_entries()
            card = build_panel_card({**panel_info, "command_entries": command_entries})
            fallback_text = self._build_panel_commands_text(command_entries)
        elif args.view == "status":
            status_entries = self._build_panel_status_entries(session)
            card = build_panel_card({**panel_info, "status_entries": status_entries})
            fallback_text = self._build_panel_status_text(status_entries)
        else:
            entries = self.session_browser.list_entries(session_key, session, limit=6)
            directory_shortcuts = self.shortcuts.build_directory_shortcut_entries(session)
            card = build_panel_card(
                {
                    **panel_info,
                    "sessions": self.session_ux.build_session_display_entries(entries),
                    "directory_shortcuts": directory_shortcuts,
                }
            )
            fallback_text = self._build_panel_home_text(session, entries, directory_shortcuts)
        try:
            await self.messenger.send_interactive_card(
                message.chat_id,
                card,
                reply_to_message_id=self.reply_policy.command_reply_target(message),
                root_id=self.reply_policy.root_id_for_message(message),
                force_new_message=self.reply_policy.should_force_new_message_for_command_card(message),
                update_message_id=self.reply_policy.command_card_update_target(message),
            )
        except Exception:
            await self.reply_fallback(message, fallback_text, "/panel")

    async def send_session_list(
        self,
        message: IncomingMessage,
        session_key: str,
        session: SessionRecord,
        page: int,
        sort_mode: SessionSortMode,
    ) -> None:
        session_page = self.session_browser.list_page(session_key, session, page=page, sort_mode=sort_mode)
        card = build_session_list_card(
            {
                "session_id": session.session_id,
                "current_title": self.session_ux.build_session_title(session.label, session.session_id),
                "channel": format_release_channel(infer_release_channel(self.config, session)),
                "cwd": self.workspace.format_cwd(session.cwd, session),
                "page": session_page.page,
                "total_pages": session_page.total_pages,
                "total_entries": session_page.total_entries,
                "sort_mode": session_page.sort_mode,
                "has_previous": session_page.has_previous,
                "has_next": session_page.has_next,
                "action_context": self.reply_policy.build_card_action_context(message, session_key),
                "sessions": self.session_ux.build_session_display_entries(session_page.entries, start_index=session_page.start_index),
            }
        )
        try:
            await self.messenger.send_interactive_card(
                message.chat_id,
                card,
                reply_to_message_id=self.reply_policy.command_reply_target(message),
                root_id=self.reply_policy.root_id_for_message(message),
                force_new_message=self.reply_policy.should_force_new_message_for_command_card(message),
                update_message_id=self.reply_policy.command_card_update_target(message),
            )
        except Exception:
            await self.reply_fallback(message, self.session_ux.format_session_list_page(session_page), "/resume")

    def _build_panel_base_info(self, message: IncomingMessage, session_key: str, session: SessionRecord, view: str) -> dict[str, Any]:
        return {
            "view": view,
            "session_id": session.session_id,
            "current_title": self.session_ux.build_session_title(session.label, session.session_id),
            "channel": format_release_channel(infer_release_channel(self.config, session)),
            "cwd": self.workspace.format_cwd(session.cwd, session),
            "model": self.session_ux.effective_model(session),
            "provider": self.backend_descriptors.get(session.backend).transport if session.backend in self.backend_descriptors else "-",
            "sandbox": session.safety_mode,
            "context_usage": self.session_ux.format_context_usage(session),
            "context_preview": self.session_ux.build_context_preview(session),
            "action_context": self.reply_policy.build_card_action_context(message, session_key),
        }

    def _build_panel_command_entries(self) -> list[dict[str, str]]:
        return [
            {
                "title": "恢复上一条",
                "meta": "会话 · 最短继续路径",
                "preview": "直接回到最近会话，不必先打开列表。",
                "command": "/resume latest",
                "action_label": "恢复上一条",
                "action_type": "primary",
            },
            {
                "title": "浏览会话结果",
                "meta": "会话 · 翻页 / 排序",
                "preview": "在面板里看最近会话，再决定恢复哪一条。",
                "command": "/panel sessions",
                "action_label": "看会话",
            },
            {
                "title": "浏览目录结果",
                "meta": "目录 · 快捷入口",
                "preview": "优先点快捷目录；没有合适入口时再手写 /cwd。",
                "command": "/panel directories",
                "action_label": "看目录",
            },
            {
                "title": "管理快捷目录",
                "meta": "目录 · 新增 / 列表 / 快速切换",
                "preview": "用 /shortcut add|list|cd 在飞书里维护自己的常用目录入口。",
                "command": "/shortcut list",
                "action_label": "看快捷目录",
            },
            {
                "title": "查看完整状态",
                "meta": "状态 · 目录 / 模型 / 上下文",
                "preview": "先确认现场，再决定继续当前任务还是切上下文。",
                "command": "/status",
                "action_label": "看状态",
            },
            {
                "title": "新建隔离会话",
                "meta": "隔离 · 新任务 / 切话题",
                "preview": "当目标已经变了时，不要继续堆在当前会话里。",
                "command": "/new",
                "action_label": "新会话",
            },
            {
                "title": "打开帮助",
                "meta": "引导 · 下一步建议",
                "preview": "需要 prompt 示例或命令速查时使用。",
                "command": "/help",
                "action_label": "打开帮助",
            },
        ]

    def _build_panel_status_entries(self, session: SessionRecord) -> list[dict[str, str]]:
        channel = format_release_channel(infer_release_channel(self.config, session))
        cwd = self.workspace.format_cwd(session.cwd, session)
        context_preview = self.session_ux.build_context_preview(session) or "还没有可总结的本地上下文。"
        return [
            {
                "title": "当前会话状态",
                "meta": f"{channel} · 目录 {cwd} · sandbox {session.safety_mode}",
                "preview": f"模型 {self.session_ux.effective_model(session)} · 后端线程 {session.native_session_id or 'pending'}",
                "command": "/status",
                "action_label": "完整状态",
                "action_type": "primary",
            },
            {
                "title": "上下文与用量",
                "meta": f"context_usage={self.session_ux.format_context_usage(session)}",
                "preview": context_preview,
                "command": "/usage",
                "action_label": "查看用量",
            },
            {
                "title": "继续当前任务",
                "meta": "如果目标没变，通常直接发消息最快",
                "preview": "要找旧会话就去会话结果；要切目录就去目录结果；不确定下一步时再打开帮助。",
                "command": "/help",
                "action_label": "打开帮助",
            },
        ]

    def _build_panel_home_text(self, session: SessionRecord, entries: list[Any], directory_shortcuts: list[dict[str, str]]) -> str:
        lines = [
            "OpenRelay 面板",
            f"当前会话={self.session_ux.shorten(session.label or session.session_id, 40)}",
            f"session_id={session.session_id}",
            f"channel={format_release_channel(infer_release_channel(self.config, session))}",
            f"cwd={self.workspace.format_cwd(session.cwd, session)}",
            f"model={self.session_ux.effective_model(session)}",
            f"sandbox={session.safety_mode}",
            "",
            "结果面：/panel sessions | /panel directories | /panel commands | /panel status",
            "提示：/panel 现在是总入口；先选会话 / 目录 / 命令 / 状态，再进入对应结果面。",
            "目录入口仍复用 /cwd 主路径；如需强制切回稳定版本，发送 /main 原因。",
            "",
            "最近会话：",
            self.session_ux.format_session_list(entries[:3]),
        ]
        if directory_shortcuts:
            lines.extend(["", "目录入口："])
            lines.extend([f"- {entry['label']} -> {entry['display_path']}" for entry in directory_shortcuts[:3]])
            lines.append("面板里的快捷目录按钮会直接执行稳定的 /cwd 切换。")
        else:
            lines.extend(["", "目录入口：暂无快捷目录；可先 /cwd <path>。"])
        lines.extend([
            "",
            "commands: /panel sessions /panel directories /panel commands /panel status /resume list /resume latest /cwd <path> /main /develop /new /status /model [name|default] /sandbox [mode] /clear",
        ])
        return "\n".join(lines)

    def _build_panel_sessions_text(self, session_page: Any) -> str:
        return "\n".join([
            "OpenRelay 面板 · 会话",
            self.session_ux.format_session_list_page(session_page),
            "",
            "返回总览：/panel。",
        ])

    def _build_panel_directories_text(self, directory_shortcuts: list[dict[str, str]]) -> str:
        lines = [
            "OpenRelay 面板 · 目录",
            "优先点快捷目录；没有合适入口时，再手写 /cwd <path>。",
        ]
        if directory_shortcuts:
            lines.extend([f"- {entry['label']} -> {entry['display_path']}" for entry in directory_shortcuts])
        else:
            lines.append("- 当前没有配置快捷目录。")
        lines.extend(["", "常用动作：/cwd /main /develop"])
        return "\n".join(lines)

    def _build_panel_commands_text(self, command_entries: list[dict[str, str]]) -> str:
        lines = ["OpenRelay 面板 · 命令", "高频动作："]
        lines.extend([f"- {entry['title']}：{entry['preview']} ({entry['command']})" for entry in command_entries])
        return "\n".join(lines)

    def _build_panel_status_text(self, status_entries: list[dict[str, str]]) -> str:
        lines = ["OpenRelay 面板 · 状态", "先看现场，再决定下一步："]
        lines.extend([f"- {entry['title']}：{entry['preview']} ({entry['command']})" for entry in status_entries])
        return "\n".join(lines)
