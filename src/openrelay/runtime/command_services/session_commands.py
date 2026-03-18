from __future__ import annotations

from openrelay.core import SAFETY_MODES, SessionRecord
from openrelay.presentation.session import SessionPresentation
from openrelay.session import SessionMutationService


class SessionCommandService:
    def __init__(self, session_mutations: SessionMutationService, session_presentation: SessionPresentation) -> None:
        self.session_mutations = session_mutations
        self.session_presentation = session_presentation

    def clear_context(self, session_key: str, session: SessionRecord) -> None:
        self.session_mutations.clear_context(session_key, session)

    def reset_scope(self, session_key: str) -> None:
        self.session_mutations.reset_scope(session_key)

    def current_model_text(self, session: SessionRecord) -> str:
        return f"model={self.session_presentation.effective_model(session)}"

    def switch_model(self, session_key: str, session: SessionRecord, arg_text: str) -> SessionRecord:
        return self.session_mutations.switch_model(
            session_key,
            session,
            "" if arg_text.lower() in {"default", "reset", "clear"} else arg_text,
        )

    def current_sandbox_text(self, session: SessionRecord) -> str:
        return f"sandbox={session.safety_mode}"

    def validate_sandbox_mode(self, mode: str) -> bool:
        return mode in SAFETY_MODES

    def switch_sandbox(self, session_key: str, session: SessionRecord, mode: str) -> SessionRecord:
        return self.session_mutations.switch_sandbox(session_key, session, mode)

    def switch_backend(self, session_key: str, session: SessionRecord, backend: str) -> SessionRecord:
        return self.session_mutations.switch_backend(session_key, session, backend)
