from __future__ import annotations

import logging

from openrelay.core import AppConfig, IncomingMessage
from openrelay.storage import StateStore


class SessionScopeResolver:
    def __init__(self, config: AppConfig, store: StateStore, logger: logging.Logger) -> None:
        self.config = config
        self.store = store
        self.logger = logger

    def compose_key(self, message: IncomingMessage, *, thread_id: str = "") -> str:
        parts = [message.chat_type or "unknown", message.chat_id]
        if thread_id:
            parts.extend(["thread", thread_id])
        if message.chat_type == "group" and self.config.feishu.group_session_scope != "shared":
            parts.extend(["sender", message.session_owner_open_id or message.sender_open_id or "unknown"])
        return ":".join(parts)

    def thread_candidates(self, message: IncomingMessage) -> list[str]:
        return [self.compose_key(message, thread_id=thread_id) for thread_id in self._thread_ids(message)]

    def build_session_key(self, message: IncomingMessage) -> str:
        if message.session_key:
            resolved = self.store.find_session_key_alias(message.session_key) or message.session_key
            self.logger.info(
                "session_key resolved from explicit key event_id=%s message_id=%s explicit=%s resolved=%s",
                message.event_id,
                message.message_id,
                message.session_key,
                resolved,
            )
            return resolved
        root_id = str(message.root_id or "").strip()
        if root_id:
            root_session_key = self.compose_key(message, thread_id=root_id)
            resolved_root = self.store.find_session_key_alias(root_session_key) or root_session_key
            self.logger.info(
                "session_key resolved from root_id event_id=%s message_id=%s root_id=%s resolved=%s",
                message.event_id,
                message.message_id,
                root_id,
                resolved_root,
            )
            return resolved_root
        thread_candidates = self.thread_candidates(message)
        if thread_candidates:
            for candidate in thread_candidates:
                resolved = self.store.find_session_key_alias(candidate)
                if resolved:
                    self.logger.info(
                        "session_key resolved from alias event_id=%s message_id=%s candidates=%s matched_candidate=%s resolved=%s",
                        message.event_id,
                        message.message_id,
                        thread_candidates,
                        candidate,
                        resolved,
                    )
                    return resolved
            for candidate in thread_candidates:
                if self.store.has_session_scope(candidate):
                    self.logger.info(
                        "session_key resolved from existing scope event_id=%s message_id=%s candidates=%s matched_candidate=%s",
                        message.event_id,
                        message.message_id,
                        thread_candidates,
                        candidate,
                    )
                    return candidate
            self.logger.info(
                "session_key using first thread candidate event_id=%s message_id=%s candidates=%s chosen=%s",
                message.event_id,
                message.message_id,
                thread_candidates,
                thread_candidates[0],
            )
            return thread_candidates[0]
        if self.is_command_message(message):
            session_key = self.compose_key(message)
            self.logger.info(
                "session_key using top-level command scope event_id=%s message_id=%s resolved=%s",
                message.event_id,
                message.message_id,
                session_key,
            )
            return session_key
        session_key = self.compose_key(message, thread_id=message.message_id)
        self.logger.info(
            "session_key using message_id thread scope event_id=%s message_id=%s resolved=%s",
            message.event_id,
            message.message_id,
            session_key,
        )
        return session_key

    def remember_inbound_aliases(self, message: IncomingMessage, session_key: str) -> None:
        if self.is_card_action_message(message):
            return
        alias_source_ids = self._thread_ids(message)
        if message.message_id and message.message_id not in alias_source_ids:
            alias_source_ids.append(message.message_id)
        for alias_source_id in alias_source_ids:
            alias_key = self.compose_key(message, thread_id=alias_source_id)
            self.store.save_session_key_alias(alias_key, session_key)
            self.logger.info(
                "saved inbound session alias event_id=%s message_id=%s alias_key=%s session_key=%s",
                message.event_id,
                message.message_id,
                alias_key,
                session_key,
            )

    def remember_outbound_aliases(
        self,
        message: IncomingMessage,
        session_key: str,
        alias_groups: tuple[tuple[str, ...], ...] | list[tuple[str, ...]],
    ) -> None:
        for alias_ids in alias_groups:
            for message_id in alias_ids:
                alias = str(message_id or "").strip()
                if not alias:
                    continue
                alias_key = self.compose_key(message, thread_id=alias)
                self.store.save_session_key_alias(alias_key, session_key)
                self.logger.info(
                    "saved outbound session alias event_id=%s message_id=%s alias_key=%s session_key=%s",
                    message.event_id,
                    message.message_id,
                    alias_key,
                    session_key,
                )

    def is_command_message(self, message: IncomingMessage) -> bool:
        return str(message.text or "").strip().startswith("/")

    def is_top_level_message(self, message: IncomingMessage) -> bool:
        return not message.root_id and not message.thread_id

    def is_top_level_control_command(self, message: IncomingMessage) -> bool:
        return self.is_top_level_message(message) and self.is_command_message(message)

    def is_card_action_message(self, message: IncomingMessage) -> bool:
        return message.event_id.startswith("card-action-")

    def root_id_for_message(self, message: IncomingMessage) -> str:
        return message.root_id or message.thread_id

    def _thread_ids(self, message: IncomingMessage) -> list[str]:
        thread_ids: list[str] = []
        for value in (message.root_id, message.thread_id, message.parent_id, message.reply_to_message_id):
            thread_id = str(value or "").strip()
            if thread_id and thread_id not in thread_ids:
                thread_ids.append(thread_id)
        return thread_ids
