from __future__ import annotations

from dataclasses import dataclass

from openrelay.core import IncomingMessage, SessionRecord
from openrelay.session import SessionLifecycleResolver, SessionScopeResolver

from .dispatch_models import DispatchDecision, ResolvedMessageContext


@dataclass(slots=True)
class MessageDispatchService:
    session_scope: SessionScopeResolver
    session_lifecycle: SessionLifecycleResolver

    def resolve(self, message: IncomingMessage) -> ResolvedMessageContext:
        session_key = self.session_scope.build_session_key(message)
        self.session_scope.remember_inbound_aliases(message, session_key)
        is_top_level_control_command = self.session_scope.is_top_level_control_command(message)
        resolved_session = self.session_lifecycle.load_for_message(
            session_key,
            is_top_level_control_command=is_top_level_control_command,
            is_top_level_message=self.session_scope.is_top_level_message(message),
            control_key=self.session_scope.compose_key(message),
        )
        return ResolvedMessageContext(
            message=message,
            session_key=session_key,
            session=resolved_session,
            is_top_level_control_command=is_top_level_control_command,
            is_top_level_message=self.session_scope.is_top_level_message(message),
            control_key=self.session_scope.compose_key(message),
        )

    def decide(
        self,
        resolved: ResolvedMessageContext,
        *,
        execution_key: str | None = None,
    ) -> DispatchDecision:
        message = resolved.message
        stripped = str(message.text or "").strip()
        command_name = stripped.split(maxsplit=1)[0].lower() if stripped.startswith("/") else ""
        kind = "turn"
        if not stripped and not message.local_image_paths:
            kind = "ignored"
        elif command_name == "/stop":
            kind = "stop"
        elif command_name:
            kind = "command"
        return DispatchDecision(
            kind=kind,
            resolved=resolved,
            execution_key=execution_key or self.build_execution_key(resolved.session_key, resolved.session),
            command_name=command_name,
        )

    def resolve_and_decide(self, message: IncomingMessage) -> DispatchDecision:
        resolved = self.resolve(message)
        return self.decide(resolved)

    def build_execution_key(self, session_key: str, session: SessionRecord) -> str:
        return f"session:{session.session_id}"
