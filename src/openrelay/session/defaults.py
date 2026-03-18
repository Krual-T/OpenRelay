from __future__ import annotations

from dataclasses import dataclass

from openrelay.core import AppConfig, SessionRecord, get_release_workspace, infer_release_channel


@dataclass(slots=True)
class SessionDefaultsPolicy:
    config: AppConfig

    def default_backend(self) -> str:
        return self.config.backend.default_backend

    def default_model(self) -> str:
        return self.config.backend.default_model

    def default_safety_mode(self) -> str:
        return self.config.backend.default_safety_mode

    def default_workspace(self, release_channel: str) -> str:
        return str(get_release_workspace(self.config, release_channel or "main"))

    def resolve_release_channel(self, session: SessionRecord | None = None, requested: str = "") -> str:
        if requested:
            return requested
        if session is not None and session.release_channel:
            return session.release_channel
        if session is not None:
            return infer_release_channel(self.config, session)
        return "main"
