import pytest

from openrelay.feishu.messenger import FeishuMessenger


class _MessengerUnderTest(FeishuMessenger):
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def patch_message(self, message_id: str, content: str) -> dict[str, object]:
        self.calls.append(("patch", message_id, content))
        return {}

    async def reply_message(self, message_id: str, msg_type: str, content: str, *, reply_in_thread: bool = True) -> dict[str, object]:
        self.calls.append(("reply", message_id, msg_type, content, reply_in_thread))
        return {"data": {"message_id": "om_reply"}}

    async def create_message(self, chat_id: str, msg_type: str, content: str, *, root_id: str = "") -> dict[str, object]:
        self.calls.append(("create", chat_id, msg_type, content, root_id))
        return {"data": {"message_id": "om_create"}}


class _PatchFailsMessenger(_MessengerUnderTest):
    async def patch_message(self, message_id: str, content: str) -> dict[str, object]:
        self.calls.append(("patch", message_id, content))
        raise RuntimeError("patch failed")


async def test_send_interactive_card_prefers_patch_update() -> None:
    messenger = _MessengerUnderTest()

    sent = await messenger.send_interactive_card(
        "oc_1",
        {"header": {"title": {"content": "resume"}}, "elements": []},
        reply_to_message_id="om_resume_card",
        update_message_id="om_resume_card",
    )

    assert sent.message_id == "om_resume_card"
    assert [call[0] for call in messenger.calls] == ["patch"]


async def test_send_interactive_card_falls_back_to_reply_after_patch_failure() -> None:
    messenger = _PatchFailsMessenger()

    sent = await messenger.send_interactive_card(
        "oc_1",
        {"header": {"title": {"content": "resume"}}, "elements": []},
        reply_to_message_id="om_resume_card",
        update_message_id="om_resume_card",
    )

    assert sent.message_id == "om_reply"
    assert [call[0] for call in messenger.calls] == ["patch", "reply"]


@pytest.mark.asyncio
async def test_send_interactive_card_logs_nbsp_entity_flow(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    messenger = _MessengerUnderTest()
    card = {
        "schema": "2.0",
        "body": {"elements": [{"tag": "markdown", "content": "=====output=====\n&nbsp;&nbsp;&nbsp;&nbsp;return&nbsp;raw"}]},
    }

    sent = await messenger.send_interactive_card(
        "oc_1",
        card,
        reply_to_message_id="om_resume_card",
    )

    assert sent.message_id == "om_reply"
    assert any("feishu send interactive card" in record.getMessage() for record in caplog.records)
    assert "&nbsp;&nbsp;&nbsp;&nbsp;return&nbsp;raw" in messenger.calls[0][3]
