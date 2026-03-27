from __future__ import annotations

import os

from openrelay.core import AppConfig, SessionRecord, get_session_workspace_root
from openrelay.storage import StateStore

from .session import SessionPresentation


class RuntimeStatusPresenter:
    def __init__(self, config: AppConfig, store: StateStore, session_presentation: SessionPresentation) -> None:
        self.config = config
        self.store = store
        self.session_presentation = session_presentation

    def build_text(self, command_name: str, session_key: str, session: SessionRecord) -> str:
        lines = [
            f"session_base={session_key}",
            f"session_id={session.session_id}",
            f"context_label={session.label or '未命名会话'}",
            f"workspace_root={get_session_workspace_root(self.config, session)}",
            f"model={self.session_presentation.effective_model(session)}",
            f"sandbox={session.safety_mode}",
            f"cwd={self.session_presentation.format_cwd(session.cwd, session)}",
            f"messages={len(self.store.list_messages(session.session_id))}",
            f"backend_thread={session.native_session_id or 'pending'}",
            f"server_pid={os.getpid()}",
        ]
        lines.extend(self.session_presentation.build_usage_lines(session))
        if command_name == "/status":
            lines.extend(["", "最近上下文：", *self.session_presentation.build_context_lines(session)])
        return "\n".join(lines)
