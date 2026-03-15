from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from openrelay.backends import BackendDescriptor
from openrelay.core import AppConfig, IncomingMessage, SessionRecord
from openrelay.feishu import FeishuMessenger
from openrelay.presentation.panel import RuntimePanelPresenter
from openrelay.presentation.session import SessionPresentation
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
        action_context = self.reply_policy.build_card_action_context(message, session_key)
        card, fallback_text = self.presenter.build_session_list_payload(message, session_key, session, page, sort_mode, action_context)
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
