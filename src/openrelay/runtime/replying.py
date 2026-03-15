from __future__ import annotations

from dataclasses import dataclass

from openrelay.core import AppConfig, IncomingMessage
from openrelay.session import SessionScopeResolver


@dataclass(slots=True)
class ReplyRoute:
    reply_to_message_id: str
    root_id: str
    force_new_message: bool = False


class RuntimeReplyPolicy:
    def __init__(self, config: AppConfig, session_scope: SessionScopeResolver) -> None:
        self.config = config
        self.session_scope = session_scope

    def default_route(self, message: IncomingMessage) -> ReplyRoute:
        return ReplyRoute(
            reply_to_message_id=message.reply_to_message_id or ("" if self.is_card_action_message(message) else message.message_id),
            root_id=self.root_id_for_message(message),
        )

    def streaming_route(self, message: IncomingMessage) -> ReplyRoute:
        if self.is_top_level_session_start(message):
            return ReplyRoute(reply_to_message_id="", root_id=message.message_id, force_new_message=True)
        return self.default_route(message)

    def command_route(self, message: IncomingMessage, command_name: str) -> ReplyRoute:
        return ReplyRoute(
            reply_to_message_id=self.command_reply_target(message),
            root_id=self.root_id_for_message(message),
            force_new_message=self.should_force_new_message_for_command(message, command_name),
        )

    def command_reply_target(self, message: IncomingMessage) -> str:
        return message.reply_to_message_id or ("" if self.is_card_action_message(message) else message.message_id)

    def command_card_update_target(self, message: IncomingMessage) -> str:
        if not self.is_card_action_message(message):
            return ""
        return message.reply_to_message_id

    def should_force_new_message_for_command(self, message: IncomingMessage, command_name: str) -> bool:
        if not self.is_top_level_p2p_command(message):
            return False
        return command_name not in {"/cwd", "/cd"}

    def should_force_new_message_for_command_card(self, message: IncomingMessage) -> bool:
        return self.is_top_level_p2p_command(message) and not self.is_card_action_message(message)

    def build_card_action_context(self, message: IncomingMessage, session_key: str) -> dict[str, str]:
        return {
            "rootId": message.root_id,
            "threadId": message.thread_id or message.root_id,
            "sessionKey": session_key,
            "sessionOwnerOpenId": message.session_owner_open_id or (
                message.sender_open_id
                if message.chat_type == "group" and self.config.feishu.group_session_scope != "shared"
                else ""
            ),
        }

    def root_id_for_message(self, message: IncomingMessage) -> str:
        return self.session_scope.root_id_for_message(message)

    def is_card_action_message(self, message: IncomingMessage) -> bool:
        return self.session_scope.is_card_action_message(message)

    def is_top_level_p2p_command(self, message: IncomingMessage) -> bool:
        return message.chat_type == "p2p" and not message.root_id and not message.thread_id

    def is_top_level_session_start(self, message: IncomingMessage) -> bool:
        return not self.is_card_action_message(message) and not message.root_id and not message.thread_id and not str(message.text or "").strip().startswith("/")
