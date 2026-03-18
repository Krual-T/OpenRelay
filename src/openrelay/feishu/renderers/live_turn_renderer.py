from __future__ import annotations

from typing import Any

from openrelay.agent_runtime import LiveTurnViewModel
from openrelay.presentation.live_turn_view_builder import LiveTurnViewBuilder
from openrelay.presentation.models import TurnViewSnapshot

from openrelay.feishu.reply_card import build_complete_card, build_streaming_card_json, build_streaming_content, build_streaming_card_signature, render_transcript_markdown


class FeishuLiveTurnRenderer:
    def __init__(self) -> None:
        self.builder = LiveTurnViewBuilder()

    def build_reply_card(self, text: object, *, transcript_markdown: object = "") -> dict[str, Any]:
        return build_complete_card(text, transcript_markdown=transcript_markdown)

    def build_streaming_card(self, state: dict[str, Any] | TurnViewSnapshot | LiveTurnViewModel) -> dict[str, Any]:
        return build_complete_card(
            self._snapshot_dict(state).get("partial_text") or "",
            transcript_markdown=self.render_transcript_markdown(state),
        )

    def build_final_card(self, state: dict[str, Any] | TurnViewSnapshot | LiveTurnViewModel, *, fallback_text: str = "") -> dict[str, Any]:
        snapshot = self._snapshot_dict(state)
        text = str(fallback_text or snapshot.get("partial_text") or "").strip() or "回复为空。"
        process_text = self.render_transcript_markdown(snapshot, include_summary=False)
        return build_complete_card(text, panel_text=process_text)

    def render_transcript_markdown(
        self,
        state: dict[str, Any] | TurnViewSnapshot | LiveTurnViewModel,
        *,
        include_summary: bool = True,
    ) -> str:
        return self.builder.build_transcript_markdown(state, include_summary=include_summary)

    def build_streaming_card_json(self, state: dict[str, Any] | TurnViewSnapshot | LiveTurnViewModel) -> dict[str, Any]:
        return build_streaming_card_json(self._snapshot_dict(state))

    def build_streaming_content(self, state: dict[str, Any] | TurnViewSnapshot | LiveTurnViewModel) -> str:
        return build_streaming_content(self._snapshot_dict(state))

    def build_streaming_card_signature(self, state: dict[str, Any] | TurnViewSnapshot | LiveTurnViewModel) -> tuple[str, str]:
        return build_streaming_card_signature(self._snapshot_dict(state))

    def _snapshot_dict(self, state: dict[str, Any] | TurnViewSnapshot | LiveTurnViewModel) -> dict[str, Any]:
        if isinstance(state, TurnViewSnapshot):
            return state.to_legacy_dict()
        if isinstance(state, LiveTurnViewModel):
            return self.builder.build_snapshot(state).to_legacy_dict()
        return dict(state)
