from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from openrelay.agent_runtime import ListSessionsRequest
from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.backends import BackendDescriptor
from openrelay.core import AppConfig, IncomingMessage, SessionRecord
from openrelay.feishu import FeishuMessenger
from openrelay.presentation.panel import RuntimePanelPresenter
from openrelay.presentation.session import SessionPresentation, build_native_thread_list_card
from openrelay.session import DEFAULT_SESSION_LIST_PAGE_SIZE
from openrelay.session.browser import SessionBrowser, SessionSortMode
from openrelay.session.shortcuts import SessionShortcutService
from openrelay.session.workspace import SessionWorkspaceService

from .commands import PanelCommandArgs
from .replying import RuntimeReplyPolicy


FallbackReply = Callable[[IncomingMessage, str, str], Awaitable[None]]


@dataclass(slots=True)
class RuntimePanelService:
    config: AppConfig
    messenger: FeishuMessenger
    backend_descriptors: dict[str, BackendDescriptor]
    session_browser: SessionBrowser
    session_presentation: SessionPresentation
    workspace: SessionWorkspaceService
    shortcuts: SessionShortcutService
    reply_policy: RuntimeReplyPolicy
    reply_fallback: FallbackReply
    presenter: RuntimePanelPresenter
    runtime_service: AgentRuntimeService | None = None

    async def send_panel(self, message: IncomingMessage, session_key: str, session: SessionRecord, args: PanelCommandArgs) -> None:
        action_context = self.reply_policy.build_card_action_context(message, session_key)
        card, fallback_text = self.presenter.build_panel_payload(message, session_key, session, args, action_context)
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
        _ = session_key, sort_mode
        action_context = self.reply_policy.build_card_action_context(message, session_key)
        card, fallback_text = await self._build_native_thread_list_payload(message, session, page, action_context)
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
            await self.reply_fallback(message, fallback_text, "/resume")

    async def _build_native_thread_list_payload(
        self,
        message: IncomingMessage,
        session: SessionRecord,
        page: int,
        action_context: dict[str, str],
    ) -> tuple[dict[str, object], str]:
        _ = message
        if self.runtime_service is None or session.backend not in self.runtime_service.backends:
            fallback = "当前后端不支持 `/resume` 原生命令。"
            return build_native_thread_list_card({"action_context": action_context, "page": max(page, 1), "current_thread_id": session.native_session_id}), fallback

        rows, _cursor = await self.runtime_service.list_sessions(
            session.backend,
            ListSessionsRequest(
                limit=max(DEFAULT_SESSION_LIST_PAGE_SIZE * max(page, 1) + 1, DEFAULT_SESSION_LIST_PAGE_SIZE + 1),
                cwd=session.cwd,
            ),
        )
        return self._build_thread_list_card_from_rows(
            session,
            page,
            action_context,
            [
                {
                    "thread_id": row.native_session_id,
                    "preview": row.preview,
                    "cwd": row.cwd,
                    "updated_at": row.updated_at,
                    "status": row.status,
                    "name": row.title,
                }
                for row in rows
            ],
        )

    def _build_thread_list_card_from_rows(
        self,
        session: SessionRecord,
        page: int,
        action_context: dict[str, str],
        threads: list[dict[str, str]],
    ) -> tuple[dict[str, object], str]:
        thread_entries: list[dict[str, object]] = []
        start = (max(page, 1) - 1) * DEFAULT_SESSION_LIST_PAGE_SIZE
        visible_threads = threads[start:start + DEFAULT_SESSION_LIST_PAGE_SIZE]
        for index, row in enumerate(visible_threads, start=start + 1):
            thread_id = str(row.get("thread_id") or "").strip()
            preview = self.session_presentation.shorten(str(row.get("preview") or ""), 96)
            title = str(row.get("name") or preview or thread_id or f"thread {index}")
            meta: list[str] = []
            updated_at = str(row.get("updated_at") or "").strip()
            if updated_at:
                meta.append(updated_at[:16].replace("T", " "))
            status = str(row.get("status") or "").strip()
            if status:
                meta.append(f"status={status}")
            cwd = str(row.get("cwd") or "").strip()
            if cwd:
                meta.append(f"cwd={self.workspace.format_cwd(cwd, session)}")
            meta.append(f"id={thread_id}")
            thread_entries.append(
                {
                    "index": index,
                    "thread_id": thread_id,
                    "active": thread_id == session.native_session_id,
                    "title": self.session_presentation.shorten(title, 56),
                    "meta": " · ".join(meta),
                    "preview": preview,
                }
            )

        card = build_native_thread_list_card(
            {
                "page": max(page, 1),
                "has_previous": page > 1,
                "has_next": start + DEFAULT_SESSION_LIST_PAGE_SIZE < len(threads),
                "current_thread_id": session.native_session_id,
                "action_context": action_context,
                "threads": thread_entries,
            }
        )
        lines = [f"Codex 会话列表（第 {max(page, 1)} 页）："]
        if thread_entries:
            for entry in thread_entries:
                lines.append(f"{entry['index']}. {entry['title']}")
                lines.append(f"   {entry['meta']}")
                if entry["preview"]:
                    lines.append(f"   预览：{entry['preview']}")
        else:
            lines.append("当前没有可连接的 Codex 会话。")
        lines.extend(["", "直接点卡片按钮即可连接；也可以手输 `/resume <thread_id>`。"])
        return card, "\n".join(lines)
