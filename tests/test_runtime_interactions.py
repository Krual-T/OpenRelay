from __future__ import annotations

import asyncio

import pytest

from openrelay.agent_runtime import ApprovalDecision, ApprovalRequest
from openrelay.core import IncomingMessage
from openrelay.runtime.interactions import RunInteractionController


class FakeMessenger:
    def __init__(self) -> None:
        self.cards: list[dict] = []

    async def send_interactive_card(
        self,
        chat_id: str,
        card: dict,
        *,
        reply_to_message_id: str = "",
        root_id: str = "",
        force_new_message: bool = False,
        update_message_id: str = "",
    ) -> object:
        _ = chat_id, reply_to_message_id, root_id, force_new_message, update_message_id
        self.cards.append(card)
        return object()


def _extract_card_commands(card: dict) -> list[str]:
    commands: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        if node.get("tag") == "action":
            for action in node.get("actions", []):
                if isinstance(action, dict):
                    value = action.get("value")
                    if isinstance(value, dict):
                        command = str(value.get("command") or "").strip()
                        if command:
                            commands.append(command)
        for value in node.values():
            walk(value)

    walk(card)
    return commands


@pytest.mark.asyncio
async def test_interaction_controller_accepts_unified_approval_request_without_provider_method() -> None:
    messenger = FakeMessenger()
    progress_events: list[dict] = []
    text_messages: list[str] = []
    controller = RunInteractionController(
        messenger,
        chat_id="oc_1",
        root_id="om_root",
        action_context={},
        reply_target_getter=lambda: "om_reply",
        emit_progress=lambda event: _record_progress(progress_events, event),
        send_text=lambda text: _record_text(text_messages, text),
        cancel_event=None,
    )

    decision_task = asyncio.create_task(
        controller.request_approval(
            ApprovalRequest(
                approval_id="approval_1",
                session_id="relay_1",
                turn_id="turn_1",
                kind="command",
                title="Command Approval Required",
                description="Command: pytest -q",
                payload={
                    "request_id": "approval_1",
                    "command": "pytest -q",
                    "cwd": "/workspace",
                    "reason": "Run tests before continue",
                },
                options=("accept", "accept_for_session", "decline", "cancel"),
                provider_payload={},
            )
        )
    )

    for _ in range(20):
        if messenger.cards:
            break
        await asyncio.sleep(0)
    assert messenger.cards

    allow_once_command = next(
        command
        for command in _extract_card_commands(messenger.cards[-1])
        if command.endswith(" accept")
    )
    handled = await controller.try_handle_message(
        IncomingMessage(
            event_id="evt_accept",
            message_id="om_accept",
            chat_id="oc_1",
            chat_type="p2p",
            sender_open_id="ou_user",
            text=allow_once_command,
            actionable=True,
            reply_to_message_id="om_interaction_card",
        )
    )

    assert handled is True
    assert await decision_task == ApprovalDecision(decision="accept")
    assert [event["type"] for event in progress_events] == ["interaction.requested", "interaction.resolved"]
    assert text_messages == []


async def _record_progress(store: list[dict], event: dict) -> None:
    store.append(event)


async def _record_text(store: list[str], text: str) -> None:
    store.append(text)
