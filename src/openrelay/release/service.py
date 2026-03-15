from __future__ import annotations

from dataclasses import dataclass

from openrelay.core import (
    AppConfig,
    SessionRecord,
    append_release_event,
    build_release_session_label,
    build_release_switch_note,
    get_release_workspace,
    infer_release_channel,
)
from openrelay.presentation.session import SessionPresentation
from openrelay.session import SessionMutationService
from openrelay.storage import StateStore


@dataclass(slots=True)
class ReleaseSwitchResult:
    session: SessionRecord
    event: dict[str, object]
    cancelled_active_run: bool


class ReleaseCommandService:
    def __init__(
        self,
        config: AppConfig,
        store: StateStore,
        session_ux: SessionPresentation,
        session_mutations: SessionMutationService,
    ) -> None:
        self.config = config
        self.store = store
        self.session_ux = session_ux
        self.session_mutations = session_mutations

    def switch_channel(
        self,
        *,
        session_key: str,
        session: SessionRecord,
        target_channel: str,
        command_name: str,
        reason: str,
        chat_id: str,
        operator_open_id: str,
        cancelled_active_run: bool,
    ) -> ReleaseSwitchResult:
        workspace_dir = get_release_workspace(self.config, target_channel)
        if not workspace_dir.exists():
            raise FileNotFoundError(f"{target_channel} 工作目录不存在：{workspace_dir}")

        next_session = self.session_mutations.switch_release_channel(
            session_key,
            session,
            target_channel,
            build_release_session_label(target_channel),
        )
        event = append_release_event(
            self.config,
            {
                "type": "release.force-stable" if target_channel == "main" else "release.switch",
                "command": command_name,
                "reason": reason,
                "session_key": session_key,
                "chat_id": chat_id,
                "operator_open_id": operator_open_id,
                "from_channel": infer_release_channel(self.config, session),
                "to_channel": target_channel,
                "previous_session_id": session.session_id,
                "next_session_id": next_session.session_id,
                "previous_cwd": session.cwd,
                "next_cwd": next_session.cwd,
                "previous_model": self.session_ux.effective_model(session),
                "next_model": self.session_ux.effective_model(next_session),
                "previous_sandbox": session.safety_mode,
                "next_sandbox": next_session.safety_mode,
                "cancelled_active_run": cancelled_active_run,
            },
        )
        self.store.append_message(next_session.session_id, "assistant", build_release_switch_note(event))
        return ReleaseSwitchResult(session=next_session, event=event, cancelled_active_run=cancelled_active_run)
