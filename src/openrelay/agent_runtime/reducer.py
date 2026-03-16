from __future__ import annotations

from dataclasses import replace

from openrelay.core import utc_now

from .events import (
    ApprovalRequestedEvent,
    ApprovalResolvedEvent,
    AssistantCompletedEvent,
    AssistantDeltaEvent,
    PlanUpdatedEvent,
    ReasoningDeltaEvent,
    RuntimeEvent,
    SessionStartedEvent,
    ToolCompletedEvent,
    ToolProgressEvent,
    ToolStartedEvent,
    TurnCompletedEvent,
    TurnFailedEvent,
    TurnInterruptedEvent,
    TurnStartedEvent,
    UsageUpdatedEvent,
)
from .models import LiveTurnViewModel, ToolState


class LiveTurnReducer:
    def __init__(self, state: LiveTurnViewModel) -> None:
        self.state = state

    def apply(self, event: RuntimeEvent) -> LiveTurnViewModel:
        self.state.updated_at = event.created_at or utc_now()
        if isinstance(event, SessionStartedEvent):
            if event.native_session_id:
                self.state.native_session_id = event.native_session_id
        elif isinstance(event, TurnStartedEvent):
            self.state.status = "running"
            if event.turn_id:
                self.state.turn_id = event.turn_id
            self.state.error_message = ""
        elif isinstance(event, AssistantDeltaEvent):
            self.state.status = "running"
            self.state.assistant_text = f"{self.state.assistant_text}{event.delta}"
        elif isinstance(event, AssistantCompletedEvent):
            self.state.assistant_text = event.text or self.state.assistant_text
        elif isinstance(event, ReasoningDeltaEvent):
            self.state.reasoning_text = event.text or self.state.reasoning_text
        elif isinstance(event, PlanUpdatedEvent):
            self.state.plan_steps = event.steps
        elif isinstance(event, ToolStartedEvent):
            self.state.status = "running"
            self._upsert_tool(event.tool)
        elif isinstance(event, ToolProgressEvent):
            self._update_tool_detail(event.tool_id, event.detail)
        elif isinstance(event, ToolCompletedEvent):
            self._upsert_tool(event.tool)
        elif isinstance(event, ApprovalRequestedEvent):
            self.state.pending_approval = event.request
        elif isinstance(event, ApprovalResolvedEvent):
            if self.state.pending_approval is not None and self.state.pending_approval.approval_id == event.approval_id:
                self.state.pending_approval = None
        elif isinstance(event, UsageUpdatedEvent):
            self.state.usage = event.usage
        elif isinstance(event, TurnCompletedEvent):
            self.state.status = "completed"
            self.state.pending_approval = None
            if event.final_text:
                self.state.assistant_text = event.final_text
            if event.usage is not None:
                self.state.usage = event.usage
            self.state.error_message = ""
        elif isinstance(event, TurnFailedEvent):
            self.state.status = "failed"
            self.state.pending_approval = None
            self.state.error_message = event.message
        elif isinstance(event, TurnInterruptedEvent):
            self.state.status = "interrupted"
            self.state.pending_approval = None
            self.state.error_message = event.message
        return self.state

    def _upsert_tool(self, tool: ToolState) -> None:
        tools = list(self.state.tools)
        for index, existing in enumerate(tools):
            if existing.tool_id == tool.tool_id:
                merged_provider_payload = dict(existing.provider_payload)
                merged_provider_payload.update(tool.provider_payload)
                tools[index] = replace(
                    tool,
                    preview=tool.preview or existing.preview,
                    detail=tool.detail or existing.detail,
                    exit_code=tool.exit_code if tool.exit_code is not None else existing.exit_code,
                    provider_payload=merged_provider_payload,
                )
                self.state.tools = tuple(tools)
                return
        tools.append(tool)
        self.state.tools = tuple(tools)

    def _update_tool_detail(self, tool_id: str, detail: str) -> None:
        if not tool_id:
            return
        tools = list(self.state.tools)
        for index, existing in enumerate(tools):
            if existing.tool_id != tool_id:
                continue
            merged_detail = f"{existing.detail}{detail}" if existing.detail and detail else (detail or existing.detail)
            tools[index] = replace(existing, detail=merged_detail)
            self.state.tools = tuple(tools)
            return


class LiveTurnRegistry:
    def __init__(self) -> None:
        self.reducers: dict[tuple[str, str], LiveTurnReducer] = {}

    def get_or_create(
        self,
        session_id: str,
        turn_id: str,
        backend: str,
        native_session_id: str,
    ) -> LiveTurnReducer:
        key = (session_id, turn_id)
        reducer = self.reducers.get(key)
        if reducer is not None:
            return reducer
        reducer = LiveTurnReducer(
            LiveTurnViewModel(
                backend=backend,  # type: ignore[arg-type]
                session_id=session_id,
                native_session_id=native_session_id,
                turn_id=turn_id,
            )
        )
        self.reducers[key] = reducer
        return reducer

    def apply(self, event: RuntimeEvent) -> LiveTurnViewModel:
        reducer = self.get_or_create(
            session_id=event.session_id,
            turn_id=event.turn_id,
            backend=event.backend,
            native_session_id=str(event.provider_payload.get("native_session_id") or ""),
        )
        return reducer.apply(event)

    def read(self, session_id: str, turn_id: str) -> LiveTurnViewModel | None:
        reducer = self.reducers.get((session_id, turn_id))
        return None if reducer is None else reducer.state

    def clear_finished(self, older_than_seconds: int) -> None:
        if older_than_seconds < 0:
            return
        removable = [
            key
            for key, reducer in self.reducers.items()
            if reducer.state.status in {"completed", "failed", "interrupted"}
        ]
        for key in removable:
            self.reducers.pop(key, None)
