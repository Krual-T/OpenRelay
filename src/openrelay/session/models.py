from __future__ import annotations

from dataclasses import dataclass, field

from openrelay.agent_runtime.models import BackendKind, SessionLocator
from openrelay.core import utc_now


@dataclass(slots=True, frozen=True)
class RelayScope:
    relay_session_id: str
    feishu_chat_id: str
    feishu_thread_id: str = ""


@dataclass(slots=True)
class RelaySessionBinding:
    relay_session_id: str
    backend: BackendKind
    native_session_id: str
    cwd: str
    model: str
    safety_mode: str
    feishu_chat_id: str
    feishu_thread_id: str
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    @property
    def locator(self) -> SessionLocator:
        return SessionLocator(backend=self.backend, native_session_id=self.native_session_id)
