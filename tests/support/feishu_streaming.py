import pytest

import openrelay.feishu.streaming as streaming_card_module
from openrelay.agent_runtime import LiveTurnViewModel, ToolState
from openrelay.feishu import (
    DEFAULT_THINKING_TEXT,
    FeishuStreamingSession,
    STREAMING_ELEMENT_ID,
    build_streaming_card_json,
    build_streaming_content,
)
from openrelay.feishu.common import summarize_text_entities
from openrelay.feishu.highlight import render_command_chunks
from openrelay.feishu.reply_card import build_complete_card, build_streaming_card_signature, optimize_markdown_style
from openrelay.presentation.live_turn import LiveTurnPresenter


class _SuccessfulResponse:
    code = 0
    msg = "ok"

    def success(self) -> bool:
        return True


class _RecordingCardElementApi:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def acontent(self, request: object) -> _SuccessfulResponse:
        self.calls.append(request)
        return _SuccessfulResponse()


class _RecordingCardApi:
    def __init__(self) -> None:
        self.update_calls: list[object] = []

    async def aupdate(self, request: object) -> _SuccessfulResponse:
        self.update_calls.append(request)
        return _SuccessfulResponse()


class _RecordingMessenger:
    def __init__(self) -> None:
        self.client = type(
            "Client",
            (),
            {
                "cardkit": type(
                    "CardKit",
                    (),
                    {
                        "v1": type(
                            "V1",
                            (),
                            {
                                "card_element": _RecordingCardElementApi(),
                                "card": _RecordingCardApi(),
                            },
                        )()
                    },
                )()
            },
        )()

    def ensure_success(self, response: object, label: str) -> None:
        _ = (response, label)
