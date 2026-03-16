from pathlib import Path

import logging
import pytest

from openrelay.agent_runtime import SessionLocator, SessionSummary, SessionTranscript
from openrelay.agent_runtime.backend import BackendCapabilities
from openrelay.agent_runtime.models import TranscriptMessage
from openrelay.core import AppConfig, BackendConfig, FeishuConfig, IncomingMessage
from openrelay.presentation.runtime_status import RuntimeStatusPresenter
from openrelay.presentation.session import SessionPresentation
from openrelay.release import ReleaseCommandService
from openrelay.runtime import HelpRenderer, RuntimeCommandHooks, RuntimeCommandRouter
from openrelay.runtime.replying import RuntimeReplyPolicy
from openrelay.session import SessionBrowser, SessionMutationService, SessionScopeResolver, SessionShortcutService, SessionWorkspaceService
from openrelay.storage import StateStore


class FakeNativeThread:
    def __init__(self, thread_id: str, *, preview: str = "", cwd: str = "", updated_at: str = "", status: str = "", name: str = "", messages: tuple[object, ...] = ()) -> None:
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


class FakeRuntimeService:
    def __init__(self, cwd: str) -> None:
        self.backends = {"codex": _RuntimeBackendStub(supports_session_list=True, supports_compact=True)}
        self.threads = [
            FakeNativeThread(
                "thread_latest",
                preview="Codex task 1",
                cwd=cwd,
                updated_at="2026-03-15T10:00:00Z",
                status="idle",
                name="task 1",
                messages=(
                    FakeNativeMessage("user", "user message 1"),
                    FakeNativeMessage("assistant", "assistant message 1"),
                ),
            )
        ]

    async def list_sessions(self, backend: str, request) -> tuple[list[SessionSummary], str]:
        assert backend == "codex"
        return (
            [
                SessionSummary(
                    backend="codex",
                    native_session_id=thread.thread_id,
                    title=thread.name,
                    preview=thread.preview,
                    cwd=thread.cwd,
                    updated_at=thread.updated_at,
                    status=thread.status,
                )
                for thread in self.threads[: request.limit]
            ],
            "",
        )

    async def read_session(self, locator: SessionLocator) -> SessionTranscript:
        for thread in self.threads:
            if thread.thread_id == locator.native_session_id:
                return SessionTranscript(
                    summary=SessionSummary(
                        backend="codex",
                        native_session_id=thread.thread_id,
                        title=thread.name,
                        preview=thread.preview,
                        cwd=thread.cwd,
                        updated_at=thread.updated_at,
                        status=thread.status,
                    ),
                    messages=tuple(TranscriptMessage(role=message.role, text=message.text) for message in thread.messages),
                )
        raise AssertionError(f"unknown thread: {locator.native_session_id}")

    async def compact_locator(self, locator: SessionLocator):
        return {"compactId": f"compact_for_{locator.native_session_id}"}


class _RuntimeBackendStub:
    def __init__(self, *, supports_session_list: bool = False, supports_compact: bool = False) -> None:
        self._capabilities = BackendCapabilities(
            supports_session_list=supports_session_list,
            supports_compact=supports_compact,
        )

    def capabilities(self) -> BackendCapabilities:
        return self._capabilities


class FakeHooks:
    def __init__(self) -> None:
        self.replies: list[dict[str, object]] = []

    async def reply(self, message: IncomingMessage, text: str, **kwargs) -> None:
        self.replies.append({"message": message, "text": text, "kwargs": kwargs})

    async def send_help(self, message: IncomingMessage, session_key: str, session, available_backends: list[str]) -> None:
        raise AssertionError("unexpected help call")

    async def send_panel(self, message: IncomingMessage, session_key: str, session, args) -> None:
        raise AssertionError("unexpected panel call")

    async def send_session_list(self, message: IncomingMessage, session_key: str, session, page: int, sort_mode: str) -> None:
        raise AssertionError("unexpected session list call")

    async def stop(self, message: IncomingMessage, session_key: str) -> None:
        raise AssertionError("unexpected stop call")

    async def cancel_active_run_for_session(self, session, command_name: str) -> bool:
        return False

    def schedule_restart(self) -> None:
        raise AssertionError("unexpected restart")

    def is_admin(self, sender_open_id: str) -> bool:
        return False

    def available_backend_names(self) -> list[str]:
        return ["codex"]


def make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        cwd=tmp_path,
        port=3100,
        webhook_path="/feishu/webhook",
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "workspace",
        main_workspace_dir=tmp_path / "main",
        develop_workspace_dir=tmp_path / "develop",
        max_request_bytes=1024,
        max_session_messages=20,
        feishu=FeishuConfig(app_id="app", app_secret="secret", verify_token="verify-token", bot_open_id="ou_bot"),
        backend=BackendConfig(default_backend="codex", codex_sessions_dir=tmp_path / "native"),
    )


def prepare_dirs(config: AppConfig) -> None:
    for path in [config.workspace_root, config.main_workspace_dir, config.develop_workspace_dir, config.backend.codex_sessions_dir]:
        path.mkdir(parents=True, exist_ok=True)


def make_message(text: str, suffix: str = "cmd") -> IncomingMessage:
    return IncomingMessage(
        event_id=f"evt_{suffix}",
        message_id=f"om_{suffix}",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id="ou_user",
        text=text,
        actionable=True,
    )


def build_router(tmp_path: Path) -> tuple[RuntimeCommandRouter, StateStore, FakeHooks, FakeRuntimeService]:
    config = make_config(tmp_path)
    prepare_dirs(config)
    store = StateStore(config)
    session_presentation = SessionPresentation(config, store)
    workspace = SessionWorkspaceService(config)
    session_scope = SessionScopeResolver(config, store, logging.getLogger("test.resume.reply"))
    hooks = FakeHooks()
    runtime_service = FakeRuntimeService(str(config.main_workspace_dir))
    router = RuntimeCommandRouter(
        config,
        store,
        SessionBrowser(config, store),
        session_scope,
        SessionMutationService(config, store, session_presentation),
        session_presentation,
        workspace,
        SessionShortcutService(config, store, workspace),
        HelpRenderer(config, store, session_presentation, workspace, SessionShortcutService(config, store, workspace)),
        ReleaseCommandService(config, store, session_presentation, SessionMutationService(config, store, session_presentation)),
        RuntimeStatusPresenter(config, store, session_presentation),
        RuntimeCommandHooks(
            reply=hooks.reply,
            send_help=hooks.send_help,
            send_panel=hooks.send_panel,
            send_session_list=hooks.send_session_list,
            stop=hooks.stop,
            schedule_restart=hooks.schedule_restart,
            is_admin=hooks.is_admin,
            available_backend_names=hooks.available_backend_names,
            cancel_active_run_for_session=hooks.cancel_active_run_for_session,
        ),
        runtime_service,
    )
    return router, store, hooks, runtime_service


def test_reply_policy_keeps_resume_on_original_message(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    prepare_dirs(config)
    store = StateStore(config)
    scope = SessionScopeResolver(config, store, logging.getLogger("test.resume.reply.policy"))
    policy = RuntimeReplyPolicy(config, scope)
    message = make_message("/resume thread_latest", suffix="resume_policy")

    route = policy.command_route(message, "/resume")

    assert route.reply_to_message_id == "om_resume_policy"
    assert route.force_new_message is False
    store.close()


@pytest.mark.asyncio
async def test_resume_success_text_is_thread_focused(tmp_path: Path) -> None:
    router, store, hooks, backend = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")
    backend.threads[0].cwd = str(Path.home() / "Projects" / "openrelay")

    await router.handle(make_message("/resume latest", suffix="resume_text"), session.base_key, session)

    text = str(hooks.replies[-1]["text"])
    assert "session_id=thread_latest" in text
    assert "cwd=~/Projects/openrelay" in text
    assert "最近更新：" in text
    assert "最近历史：" not in text
    assert "已在当前顶层对话中连接；接下来直接继续发消息即可。" in text
    assert hooks.replies[-1]["kwargs"]["command_name"] == "/resume"
    store.close()
