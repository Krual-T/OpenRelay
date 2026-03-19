from __future__ import annotations

from pathlib import Path
from typing import Any

from openrelay.core import SessionRecord
from openrelay.session import RelaySessionBinding


class InMemoryBindingStore:
    def __init__(self) -> None:
        self.bindings: dict[str, RelaySessionBinding] = {}

    def save(self, binding: RelaySessionBinding) -> None:
        self.bindings[binding.relay_session_id] = binding

    def get(self, relay_session_id: str) -> RelaySessionBinding | None:
        return self.bindings.get(relay_session_id)

    def update_native_session_id(self, relay_session_id: str, native_session_id: str) -> None:
        binding = self.bindings.get(relay_session_id)
        if binding is None:
            return
        self.bindings[relay_session_id] = RelaySessionBinding(
            relay_session_id=binding.relay_session_id,
            backend=binding.backend,
            native_session_id=native_session_id,
            cwd=binding.cwd,
            model=binding.model,
            safety_mode=binding.safety_mode,
            feishu_chat_id=binding.feishu_chat_id,
            feishu_thread_id=binding.feishu_thread_id,
            created_at=binding.created_at,
            updated_at=binding.updated_at,
        )


class FakeStore:
    def __init__(self, session: SessionRecord) -> None:
        self.session = session
        self.messages: list[tuple[str, str, str]] = []

    def save_session(self, session: SessionRecord) -> SessionRecord:
        self.session = session
        return session

    def append_message(self, session_id: str, role: str, content: str) -> None:
        self.messages.append((session_id, role, content))


class FakeTypingManager:
    async def add(self, message_id: str) -> dict[str, str]:
        return {"message_id": message_id}

    async def remove(self, state: dict[str, str]) -> None:
        _ = state


class FakeStreamingSession:
    def __init__(self) -> None:
        self.started = False
        self.active = False
        self.updates: list[dict[str, Any]] = []
        self.final_card: dict[str, Any] | None = None
        self.started_route: dict[str, str] | None = None

    async def start(self, receive_id: str, *, reply_to_message_id: str = "", root_id: str = "") -> None:
        self.started = True
        self.active = True
        self.started_route = {
            "receive_id": receive_id,
            "reply_to_message_id": reply_to_message_id,
            "root_id": root_id,
        }

    def has_started(self) -> bool:
        return self.started

    def is_active(self) -> bool:
        return self.active

    def needs_rollover(self) -> bool:
        return False

    def message_id(self) -> str:
        return "om_stream"

    def message_alias_ids(self) -> tuple[str, ...]:
        return ("om_stream",)

    async def update(self, snapshot: dict[str, Any]) -> None:
        self.updates.append(snapshot)

    async def freeze(self, live_state: dict[str, Any], *, notice_text: str = "") -> None:
        _ = live_state, notice_text

    async def close(self, final_card: dict[str, Any] | None = None) -> None:
        self.active = False
        self.final_card = final_card


def build_e2e_session(tmp_path: Path) -> SessionRecord:
    return SessionRecord(
        session_id="relay_1",
        base_key="base_1",
        backend="codex",
        cwd=str(tmp_path),
        safety_mode="workspace-write",
    )


def extract_markdown_blocks(card: dict[str, Any] | None) -> list[str]:
    blocks: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        content = node.get("content")
        if isinstance(content, str) and content.strip():
            blocks.append(content)
        for value in node.values():
            walk(value)

    walk(card or {})
    return blocks
