from __future__ import annotations

from dataclasses import replace

from openrelay.core import utc_now

from .events import (
    ApprovalRequestedEvent,
    ApprovalResolvedEvent,
    AssistantCompletedEvent,
    AssistantDeltaEvent,
    BackendNoticeEvent,
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
from .models import BackendEventRecord, LiveTurnViewModel, ToolState


class LiveTurnReducer:
    def __init__(self, state: LiveTurnViewModel) -> None:
        self.state = state

    def apply(self, event: RuntimeEvent) -> LiveTurnViewModel:
        self.state.updated_at = event.created_at or utc_now()
        match event:
            case SessionStartedEvent(native_session_id=native_session_id) if native_session_id:
                self.state.native_session_id = native_session_id
            case TurnStartedEvent(turn_id=turn_id):
                self.state.status = "running"
                if turn_id:
                    self.state.turn_id = turn_id
                self.state.error_message = ""
            case AssistantDeltaEvent(delta=delta):
                self.state.status = "running"
                self.state.assistant_text = f"{self.state.assistant_text}{delta}"
            case AssistantCompletedEvent(text=text):
                self.state.assistant_text = text or self.state.assistant_text
            case ReasoningDeltaEvent(text=text):
                self.state.reasoning_text = text or self.state.reasoning_text
            case PlanUpdatedEvent(steps=steps):
                self.state.plan_steps = steps
            case BackendNoticeEvent(level=level, message=message) if (
                event.provider_payload.get("fallback")
                or event.provider_payload.get("observe")
                or event.provider_payload.get("classification") == "observe"
            ):
                self.state.backend_events = (
                    *self.state.backend_events,
                    BackendEventRecord(
                        event_type=event.event_type,
                        level=level,
                        title=str(event.provider_payload.get("title") or "Unexpected backend event"),
                        detail=message,
                        raw_payload=dict(event.provider_payload),
                        created_at=event.created_at,
                    ),
                )
            case ToolStartedEvent(tool=tool):
                self.state.status = "running"
                self._upsert_tool(tool)
            case ToolProgressEvent(tool_id=tool_id, detail=detail):
                self._update_tool_detail(tool_id, detail)
            case ToolCompletedEvent(tool=tool):
                self._upsert_tool(tool)
            case ApprovalRequestedEvent(request=request):
                self.state.pending_approval = request
            case ApprovalResolvedEvent(approval_id=approval_id):
                if self.state.pending_approval is not None and self.state.pending_approval.approval_id == approval_id:
                    self.state.pending_approval = None
            case UsageUpdatedEvent(usage=usage):
                self.state.usage = usage
            case TurnCompletedEvent(final_text=final_text, usage=usage):
                self.state.status = "completed"
                self.state.pending_approval = None
                if final_text:
                    self.state.assistant_text = final_text
                if usage is not None:
                    self.state.usage = usage
                self.state.error_message = ""
            case TurnFailedEvent(message=message):
                self.state.status = "failed"
                self.state.pending_approval = None
                self.state.error_message = message
            case TurnInterruptedEvent(message=message):
                self.state.status = "interrupted"
                self.state.pending_approval = None
                self.state.error_message = message
            case _:
                pass
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
