from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from openrelay.agent_runtime import ListSessionsRequest
from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.backends import BackendDescriptor
from openrelay.core import AppConfig, IncomingMessage, SessionRecord
from openrelay.feishu import FeishuMessenger
from openrelay.presentation.panel import RuntimePanelPresenter
from openrelay.presentation.session import SessionPresentation, build_backend_session_list_card
from openrelay.session.browser import SessionBrowser, SessionSortMode
from openrelay.session.shortcuts import SessionShortcutService
from openrelay.session.workspace import SessionWorkspaceService

from .card_sender import CommandCardSender
from .commands import PanelCommandArgs
from .replying import RuntimeReplyPolicy


FallbackReply = Callable[[IncomingMessage, str, str], Awaitable[None]]
BACKEND_SESSION_CARD_PAGE_SIZE = 3


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

    def _card_sender(self) -> CommandCardSender:
        return CommandCardSender(self.messenger, self.reply_policy, self.reply_fallback)

    async def send_panel(self, message: IncomingMessage, session_key: str, session: SessionRecord, args: PanelCommandArgs) -> None:
        action_context = self.reply_policy.build_card_action_context(message, session_key)
        card, fallback_text = self.presenter.build_panel_payload(message, session_key, session, args, action_context)
        await self._card_sender().send(message, card, fallback_text=fallback_text, command_name="/panel")

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
        card, fallback_text = await self._build_backend_session_list_payload(message, session, page, action_context)
        await self._card_sender().send(message, card, fallback_text=fallback_text, command_name="/resume")

    async def _build_backend_session_list_payload(
        self,
        message: IncomingMessage,
        session: SessionRecord,
        page: int,
        action_context: dict[str, str],
    ) -> tuple[dict[str, object], str]:
        _ = message
        backend = None if self.runtime_service is None else self.runtime_service.backends.get(session.backend)
        if backend is None or not backend.capabilities().supports_session_list:
            fallback = "当前后端不支持 `/resume` 原生命令。"
            return (
                build_backend_session_list_card(
                    {
                        "action_context": action_context,
                        "page": max(page, 1),
                        "backend_name": session.backend,
                        "current_session_id": session.native_session_id,
                    }
                ),
                fallback,
            )

        rows, _cursor = await self.runtime_service.list_sessions(
            session.backend,
            ListSessionsRequest(
                limit=max(BACKEND_SESSION_CARD_PAGE_SIZE * (max(page, 1) + 2), BACKEND_SESSION_CARD_PAGE_SIZE * 5) + 1,
                cwd=session.cwd,
            ),
        )
        return self._build_session_list_card_from_rows(
            session,
            page,
            action_context,
            [
                {
                    "session_id": row.native_session_id,
                    "preview": row.preview,
                    "cwd": row.cwd,
                    "updated_at": row.updated_at,
                    "status": row.status,
                    "name": row.title,
                }
                for row in rows
            ],
        )

    def _build_session_list_card_from_rows(
        self,
        session: SessionRecord,
        page: int,
        action_context: dict[str, str],
        sessions: list[dict[str, str]],
    ) -> tuple[dict[str, object], str]:
        session_entries: list[dict[str, object]] = []
        start = (max(page, 1) - 1) * BACKEND_SESSION_CARD_PAGE_SIZE
        visible_sessions = sessions[start:start + BACKEND_SESSION_CARD_PAGE_SIZE]
        for index, row in enumerate(visible_sessions, start=start + 1):
            session_id = str(row.get("session_id") or "").strip()
            title = str(row.get("name") or row.get("preview") or session_id or f"session {index}")
            meta: list[str] = []
            updated_at = self._format_user_facing_time(str(row.get("updated_at") or ""))
            if updated_at:
                meta.append(updated_at)
            status = str(row.get("status") or "").strip()
            if status:
                meta.append(f"status={status}")
            cwd = str(row.get("cwd") or "").strip()
            if cwd:
                meta.append(f"cwd={self.workspace.format_cwd(cwd, session)}")
            session_entries.append(
                {
                    "index": index,
                    "session_id": session_id,
                    "active": session_id == session.native_session_id,
                    "title": self.session_presentation.shorten(title, 56),
                    "meta": " · ".join(meta),
                }
            )

        card = build_backend_session_list_card(
            {
                "page": max(page, 1),
                "known_page_count": max((len(sessions) + BACKEND_SESSION_CARD_PAGE_SIZE - 1) // BACKEND_SESSION_CARD_PAGE_SIZE, max(page, 1)),
                "has_previous": page > 1,
                "has_next": start + BACKEND_SESSION_CARD_PAGE_SIZE < len(sessions),
                "backend_name": session.backend,
                "current_session_id": session.native_session_id,
                "action_context": action_context,
                "sessions": session_entries,
            }
        )
        lines = [f"{session.backend} 会话列表（第 {max(page, 1)} 页）："]
        if session_entries:
            for entry in session_entries:
                lines.append(f"{entry['index']}. {entry['title']}")
                lines.append(f"   {entry['meta']}")
                lines.append(f"   id={entry['session_id']}")
        else:
            lines.append("当前没有可连接的后端会话。")
        lines.extend(["", "直接点卡片按钮即可连接；也可以手输 `/resume <session_id>`。"])
        return card, "\n".join(lines)

    def _format_user_facing_time(self, value: str) -> str:
        raw = value.strip()
        if not raw:
            return ""
        if raw.isdigit():
            timestamp = int(raw)
            if timestamp > 10**12:
                timestamp /= 1000
            from datetime import datetime

            return datetime.fromtimestamp(timestamp).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        try:
            from datetime import datetime

            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return raw
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
