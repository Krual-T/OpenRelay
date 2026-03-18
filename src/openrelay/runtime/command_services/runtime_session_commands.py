from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openrelay.agent_runtime import ListSessionsRequest, SessionLocator
from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.core import SessionRecord
from openrelay.presentation.session import SessionPresentation
from openrelay.session import DEFAULT_SESSION_LIST_PAGE_SIZE, SessionBrowser, SessionMutationService

from ..command_context import RuntimeSessionDetails, RuntimeSessionSummary, RuntimeTranscriptMessage


class RuntimeSessionCommandService:
    def __init__(
        self,
        runtime_service: AgentRuntimeService | None,
        session_browser: SessionBrowser,
        session_mutations: SessionMutationService,
        session_presentation: SessionPresentation,
    ) -> None:
        self.runtime_service = runtime_service
        self.session_browser = session_browser
        self.session_mutations = session_mutations
        self.session_presentation = session_presentation

    def supports_session_listing(self, session: SessionRecord) -> bool:
        if self.runtime_service is None:
            return False
        backend = self.runtime_service.backends.get(session.backend)
        return backend is not None and backend.capabilities().supports_session_list

    def supports_compact(self, session: SessionRecord) -> bool:
        if self.runtime_service is None:
            return False
        backend = self.runtime_service.backends.get(session.backend)
        return backend is not None and backend.capabilities().supports_compact

    async def list_runtime_sessions(self, session: SessionRecord, limit: int) -> list[RuntimeSessionSummary]:
        assert self.runtime_service is not None
        rows, _cursor = await self.runtime_service.list_sessions(
            session.backend,
            ListSessionsRequest(limit=limit, cwd=session.cwd),
        )
        return [
            RuntimeSessionSummary(
                session_id=row.native_session_id,
                preview=row.preview,
                cwd=row.cwd,
                updated_at=row.updated_at,
                status=row.status,
                name=row.title,
            )
            for row in rows
        ]

    async def read_runtime_session(self, session: SessionRecord, session_id: str) -> RuntimeSessionDetails:
        assert self.runtime_service is not None
        transcript = await self.runtime_service.read_session(
            SessionLocator(backend=session.backend, native_session_id=session_id)  # type: ignore[arg-type]
        )
        return RuntimeSessionDetails(
            session_id=transcript.summary.native_session_id,
            preview=transcript.summary.preview,
            cwd=transcript.summary.cwd,
            updated_at=transcript.summary.updated_at,
            status=transcript.summary.status,
            name=transcript.summary.title,
            messages=tuple(
                RuntimeTranscriptMessage(role=item.role, text=item.text)
                for item in transcript.messages
                if item.text.strip()
            ),
        )

    async def compact_runtime_session(self, session: SessionRecord, session_id: str) -> dict[str, object]:
        assert self.runtime_service is not None
        return await self.runtime_service.compact_locator(
            SessionLocator(backend=session.backend, native_session_id=session_id)  # type: ignore[arg-type]
        )

    async def resolve_resume_session_id(self, session_key: str, session: SessionRecord, target: str, page: int) -> str:
        normalized = target.strip()
        if not normalized:
            return ""
        sessions = await self.list_runtime_sessions(session, max(DEFAULT_SESSION_LIST_PAGE_SIZE * max(page, 1), 20))
        lowered = normalized.lower()
        if lowered in {"latest", "prev", "previous"}:
            return sessions[0].session_id if sessions else ""
        if normalized.isdigit():
            index = int(normalized) - 1
            if 0 <= index < len(sessions):
                return sessions[index].session_id
        for runtime_session in sessions:
            if normalized == runtime_session.session_id:
                return runtime_session.session_id
        local_match = self.session_browser.find_local_session(session_key, normalized)
        if local_match is not None:
            return local_match.native_session_id or ""
        return ""

    def bind_native_thread(self, scope_key: str, session: SessionRecord, runtime_session: RuntimeSessionDetails) -> SessionRecord:
        return self.session_mutations.bind_native_thread(
            scope_key,
            session,
            runtime_session.session_id,
            cwd=runtime_session.cwd or session.cwd,
            label=runtime_session.name or session.label,
        )

    def format_runtime_session_resume_success(self, session: SessionRecord, runtime_session: RuntimeSessionDetails) -> str:
        title = runtime_session.name or runtime_session.preview or runtime_session.session_id
        lines = [
            f"已连接 {session.backend} 会话：{title}",
            f"session_id={runtime_session.session_id}",
            f"cwd={self.format_full_cwd(runtime_session.cwd or session.cwd)}",
        ]
        updated_at = self.format_user_facing_time(runtime_session.updated_at)
        if updated_at:
            lines.append(f"最近更新：{updated_at}")
        if runtime_session.status:
            lines.append(f"status={runtime_session.status}")
        if runtime_session.preview:
            lines.extend(["", f"预览：{self.session_presentation.shorten(runtime_session.preview, 120)}"])
        lines.extend(["", "已在当前顶层对话中连接；接下来直接继续发消息即可。"])
        return "\n".join(lines)

    def format_user_facing_time(self, value: str) -> str:
        raw = value.strip()
        if not raw:
            return ""
        if raw.isdigit():
            timestamp = int(raw)
            if timestamp > 10**12:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return raw
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%Y-%m-%d %H:%M:%S")

    def format_full_cwd(self, cwd: str) -> str:
        raw = cwd.strip()
        if not raw:
            return ""
        path = Path(raw).expanduser()
        home = Path.home()
        try:
            relative = path.relative_to(home)
        except ValueError:
            return str(path)
        return "~" if str(relative) == "." else f"~/{relative}"
