from __future__ import annotations

from typing import Any

from openrelay.core import AppConfig, SessionRecord
from openrelay.feishu.cards import build_button, build_card_shell, build_section_block
from openrelay.presentation.session import SessionPresentation
from openrelay.session import SessionShortcutService, SessionWorkspaceService
from openrelay.storage import StateStore


class HelpRenderer:
    def __init__(
        self,
        config: AppConfig,
        store: StateStore,
        session_ux: SessionPresentation,
        workspace: SessionWorkspaceService,
        shortcuts: SessionShortcutService,
    ):
        self.config = config
        self.store = store
        self.session_ux = session_ux
        self.workspace = workspace
        self.shortcuts = shortcuts

    def build_text(self, session: SessionRecord, available_backends: list[str]) -> str:
        _ = session
        lines = ["OpenRelay 帮助", ""]
        for title, items in self.build_command_reference_sections(available_backends):
            lines.append(f"{title}：")
            lines.extend(items)
            lines.append("")
        return "\n".join(lines).strip()

    def build_card(self, session: SessionRecord, available_backends: list[str], action_context: dict[str, str] | None = None) -> dict[str, Any]:
        _ = session
        actions_context = action_context or {}
        elements: list[dict[str, Any]] = []
        for title, items in self.build_command_reference_sections(available_backends):
            elements.append(build_section_block(title, items, emoji="📘"))
        for group in self.build_command_button_groups(available_backends, actions_context):
            elements.append({"tag": "action", "actions": group})
        return build_card_shell("openrelay help", elements, tone="info")

    def build_command_reference_sections(self, available_backends: list[str]) -> list[tuple[str, list[str]]]:
        sections: list[tuple[str, list[str]]] = [
            (
                "会话与信息",
                [
                    "- `/help` 或 `/tools`：打开帮助。",
                    "- `/status`：查看当前会话和目录状态。",
                    "- `/usage`：查看 token 和 context usage。",
                    "- `/resume`：打开可恢复会话列表。",
                    "- `/resume latest`：连接最近的后端会话。",
                    "- `/resume <序号|session_id|local_session_id>`：连接指定历史会话。",
                    "- `/compact [latest|序号|session_id]`：对当前或指定会话做 compact。",
                ],
            ),
            (
                "工作区与目录",
                [
                    "- `/workspace`：打开工作区浏览器。",
                    "- `/workspace --page N [--path <dir>] [--query <text>]`：浏览、翻页或搜索目录。",
                    "- `/workspace open <path>`：从指定目录打开浏览器。",
                    "- `/workspace select <path>`：切到目标目录。",
                    "- `/shortcut list`：列出快捷目录。",
                    "- `/shortcut add <name> <path> [all|main|develop]`：新增快捷目录。",
                    "- `/shortcut use <name>`：切到快捷目录。",
                    "- `/shortcut remove <name>`：删除快捷目录。",
                    "- `/main` 或 `/stable`：切到 main 稳定工作区。",
                    "- `/develop`：切到 develop 修复工作区。",
                ],
            ),
            (
                "执行环境",
                [
                    "- `/model`：查看当前模型。",
                    "- `/model <name|default>`：切换模型。",
                    "- `/sandbox`：查看当前 sandbox。",
                    "- `/sandbox <read-only|workspace-write|danger-full-access>`：切换 sandbox。",
                    "- `/backend list`：查看可用 backend。",
                ],
            ),
            (
                "控制与维护",
                [
                    "- `/clear`：清空当前上下文。",
                    "- `/reset`：重置当前 scope。",
                    "- `/stop`：停止当前生成。",
                    "- `/ping`：连通性检查。",
                    "- `/restart`：重启 openrelay；仅管理员可用。",
                    "- `/panel`：已移除；改用 `/resume`、`/workspace`、`/status`。",
                ],
            ),
        ]
        if len(available_backends) > 1:
            sections[2][1].append(f"- `/backend <{'|'.join(available_backends)}>`：切换 backend。")
        return sections

    def build_command_button_groups(self, available_backends: list[str], action_context: dict[str, str]) -> list[list[dict[str, Any]]]:
        groups: list[list[tuple[str, str, str]]] = [
            [("状态", "/status", "default"), ("会话", "/resume", "primary"), ("工作区", "/workspace", "default")],
            [("模型", "/model", "default"), ("Sandbox", "/sandbox", "default"), ("停止", "/stop", "default")],
        ]
        if len(available_backends) > 1:
            groups[1].insert(2, ("后端", "/backend list", "default"))
        return [[build_button(label, command, button_type, action_context) for label, command, button_type in group] for group in groups]
