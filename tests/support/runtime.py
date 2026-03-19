from __future__ import annotations

from openrelay.agent_runtime.backend import BackendCapabilities


class FakeNativeThread:
    def __init__(
        self,
        thread_id: str,
        *,
        preview: str = "",
        cwd: str = "",
        updated_at: str = "",
        status: str = "",
        name: str = "",
        messages: tuple[object, ...] = (),
    ) -> None:
        self.thread_id = thread_id
        self.preview = preview
        self.cwd = cwd
        self.updated_at = updated_at
        self.status = status
        self.name = name
        self.messages = messages


class FakeNativeMessage:
    def __init__(self, role: str, text: str) -> None:
        self.role = role
        self.text = text


class RuntimeBackendStub:
    def __init__(self, *, supports_session_list: bool = False, supports_compact: bool = False) -> None:
        self._capabilities = BackendCapabilities(
            supports_session_list=supports_session_list,
            supports_compact=supports_compact,
        )

    def capabilities(self) -> BackendCapabilities:
        return self._capabilities
