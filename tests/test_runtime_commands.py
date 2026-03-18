import logging
from pathlib import Path

import pytest

from openrelay.agent_runtime import SessionLocator, SessionSummary, SessionTranscript
from openrelay.agent_runtime.backend import BackendCapabilities
from openrelay.agent_runtime.models import TranscriptMessage
from openrelay.core import AppConfig, BackendConfig, FeishuConfig, IncomingMessage
from openrelay.presentation.runtime_status import RuntimeStatusPresenter
from openrelay.presentation.session import SessionPresentation
from openrelay.release import ReleaseCommandService
from openrelay.runtime import HelpRenderer
from openrelay.runtime import RuntimeCommandHooks, RuntimeCommandRouter
from openrelay.session import (
    SESSION_SORT_ACTIVE,
    SessionBrowser,
    SessionMutationService,
    SessionScopeResolver,
    SessionShortcutService,
    SessionWorkspaceService,
)
from openrelay.storage import StateStore


class FakeNativeThread:
    def __init__(
        self,
        thread_id: str,
        *,
        preview: str = "",
        cwd: str = "",
        updated_at: str = "",
        status: str = "",
        name: str = "",
        messages: tuple[object, ...] = (),
    ) -> None:
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
        self.cwd = cwd
        self.list_calls: list[int] = []
        self.read_calls: list[str] = []
        self.compact_calls: list[str] = []
        self.backends = {"codex": _RuntimeBackendStub(supports_session_list=True, supports_compact=True)}
        self.threads = []
        for index in range(1, 16):
            thread_id = "thread_latest" if index == 1 else "thread_older" if index == 2 else f"thread_{index}"
            self.threads.append(
                FakeNativeThread(
                    thread_id,
                    preview=f"Codex task {index}",
                    cwd=cwd,
                    updated_at=f"2026-03-{16 - min(index, 9):02d}T10:00:00Z",
                    status="idle",
                    name=f"task {index}",
                    messages=(
                        FakeNativeMessage("user", f"user message {index}"),
                        FakeNativeMessage("assistant", f"assistant message {index}"),
                    ),
                )
            )

    async def list_sessions(self, backend: str, request) -> tuple[list[SessionSummary], str]:
        assert backend == "codex"
        self.list_calls.append(request.limit)
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
        self.read_calls.append(locator.native_session_id)
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
                    messages=tuple(
                        TranscriptMessage(role=message.role, text=message.text)
                        for message in thread.messages
                    ),
                )
        raise AssertionError(f"unknown thread: {locator.native_session_id}")

    async def compact_locator(self, locator: SessionLocator):
        self.compact_calls.append(locator.native_session_id)
        return {"compactId": "compact_1"}


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
        self.help_calls: list[tuple[str, str, tuple[str, ...]]] = []
        self.panel_calls: list[tuple[str, str, str, int, str]] = []
        self.session_list_calls: list[tuple[str, int, str]] = []
        self.stop_calls: list[str] = []
        self.cancel_calls: list[tuple[str, str]] = []
        self.restart_scheduled = 0

    async def reply(self, message: IncomingMessage, text: str, **kwargs) -> None:
        self.replies.append({"message": message, "text": text, "kwargs": kwargs})

    async def send_help(self, message: IncomingMessage, session_key: str, session, available_backends: list[str]) -> None:
        self.help_calls.append((message.message_id, session_key, tuple(available_backends)))

    async def send_panel(self, message: IncomingMessage, session_key: str, session, args) -> None:
        self.panel_calls.append((message.message_id, session_key, args.view, args.page, args.sort_mode))

    async def send_session_list(self, message: IncomingMessage, session_key: str, session, page: int, sort_mode: str) -> None:
        self.session_list_calls.append((session_key, page, sort_mode))

    async def stop(self, message: IncomingMessage, session_key: str) -> None:
        self.stop_calls.append(session_key)

    async def cancel_active_run_for_session(self, session, command_name: str) -> bool:
        self.cancel_calls.append((session.session_id, command_name))
        return False

    def schedule_restart(self) -> None:
        self.restart_scheduled += 1

    def is_admin(self, sender_open_id: str) -> bool:
        return sender_open_id == "ou_admin"

    def available_backend_names(self) -> list[str]:
        return ["claude", "codex"]



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



def make_message(text: str, sender_open_id: str = "ou_user", suffix: str = "cmd") -> IncomingMessage:
    return IncomingMessage(
        event_id=f"evt_{suffix}",
        message_id=f"om_{suffix}",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id=sender_open_id,
        text=text,
        actionable=True,
    )


def make_thread_message(text: str, suffix: str = "thread_cmd") -> IncomingMessage:
    return IncomingMessage(
        event_id=f"evt_{suffix}",
        message_id=f"om_{suffix}",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id="ou_user",
        root_id="om_root",
        thread_id="thread_1",
        text=text,
        actionable=True,
    )


def make_card_action_message(text: str, suffix: str = "card_cmd") -> IncomingMessage:
    return IncomingMessage(
        event_id=f"evt_{suffix}",
        message_id=f"om_{suffix}",
        reply_to_message_id="om_resume_card",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id="ou_user",
        source_kind="card_action",
        root_id="om_root",
        thread_id="om_root",
        text=text,
        actionable=True,
    )



def build_router(tmp_path: Path) -> tuple[RuntimeCommandRouter, StateStore, FakeHooks]:
    config = make_config(tmp_path)
    prepare_dirs(config)
    store = StateStore(config)
    session_ux = SessionPresentation(config, store)
    workspace = SessionWorkspaceService(config)
    browser = SessionBrowser(config, store)
    session_mutations = SessionMutationService(config, store, session_ux)
    session_scope = SessionScopeResolver(config, store, logging.getLogger("test.runtime.commands"))
    hooks = FakeHooks()
    runtime_service = FakeRuntimeService(str(config.main_workspace_dir))
    router = RuntimeCommandRouter(
        config,
        store,
        browser,
        session_scope,
        session_mutations,
        session_ux,
        workspace,
        SessionShortcutService(config, store, workspace),
        HelpRenderer(config, store, session_ux, workspace, SessionShortcutService(config, store, workspace)),
        ReleaseCommandService(config, store, session_ux, session_mutations),
        RuntimeStatusPresenter(config, store, session_ux),
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
    return router, store, hooks


@pytest.mark.asyncio
async def test_runtime_command_router_requires_admin_for_restart(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    handled = await router.handle(make_message("/restart", suffix="restart"), session.base_key, session)

    assert handled is True
    assert hooks.restart_scheduled == 0
    assert hooks.replies[-1]["text"] == "这个命令只允许管理员使用。"
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_delegates_panel_and_admin_restart(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message("/help", suffix="help"), session.base_key, session)
    await router.handle(make_message("/panel", suffix="panel"), session.base_key, session)
    await router.handle(make_message("/restart", sender_open_id="ou_admin", suffix="restart_admin"), session.base_key, session)

    assert hooks.help_calls == [("om_help", session.base_key, ("claude", "codex"))]
    assert hooks.panel_calls == [("om_panel", session.base_key, "home", 1, "updated-desc")]
    assert hooks.restart_scheduled == 1
    assert hooks.replies[-1]["text"] == "正在重启 openrelay，预计几秒后恢复。"
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_parses_panel_view_page_and_sort(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message(f"/panel sessions --page 2 --sort {SESSION_SORT_ACTIVE}", suffix="panel_sessions"), session.base_key, session)

    assert hooks.panel_calls == [("om_panel_sessions", session.base_key, "sessions", 2, SESSION_SORT_ACTIVE)]
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_switches_release_via_service(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message("/develop bugfix", suffix="develop"), session.base_key, session)

    switched = store.find_session(session.base_key)
    assert switched is not None
    assert switched.session_id == session.session_id
    assert switched.release_channel == "develop"
    assert hooks.cancel_calls == [(session.session_id, "/develop")]
    assert "已切到 develop 修复版本。" in str(hooks.replies[-1]["text"])
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_parses_resume_list_page_and_sort(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message(f"/resume --page 2 --sort {SESSION_SORT_ACTIVE}", suffix="resume_list"), session.base_key, session)

    assert hooks.session_list_calls == [(session.base_key, 2, SESSION_SORT_ACTIVE)]
    assert hooks.replies == []
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_requires_explicit_resume_target_or_list(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message("/resume", suffix="resume_empty"), session.base_key, session)

    assert hooks.session_list_calls == [(session.base_key, 1, "updated-desc")]
    assert hooks.replies == []
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_rejects_legacy_resume_list_alias(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message("/resume list", suffix="resume_legacy_list"), session.base_key, session)

    assert hooks.session_list_calls == []
    assert hooks.replies[-1]["text"] == "resume 参数无效：`list` 已移除；直接使用 /resume\n使用 /resume 打开后端会话卡片，或 /resume [latest|<序号>|<session_id>|<local_session_id>] 直接连接。"
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_parses_equals_style_paging_args(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message("/resume --page=3 --sort=updated-desc", suffix="resume_equals"), session.base_key, session)
    await router.handle(make_message("/panel --page=2 --sort=active-first", suffix="panel_equals"), session.base_key, session)

    assert hooks.session_list_calls == [(session.base_key, 3, "updated-desc")]
    assert hooks.replies == []
    assert hooks.panel_calls == [("om_panel_equals", session.base_key, "sessions", 2, "active-first")]
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_rejects_resume_inside_thread(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    handled = await router.handle(make_thread_message("/resume", suffix="thread_resume"), session.base_key, session)

    assert handled is True
    assert hooks.session_list_calls == []
    assert hooks.replies[-1]["text"] == "`/resume` 只允许在私聊顶层使用；子 thread 会固定绑定当前后端会话。"
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_allows_resume_card_action_pagination(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    handled = await router.handle(make_card_action_message("/resume --page 2", suffix="resume_card_page_2"), session.base_key, session)

    assert handled is True
    assert hooks.session_list_calls == [(session.base_key, 2, "updated-desc")]
    assert hooks.replies == []
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_resume_latest_binds_native_thread_and_returns_history(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message("/resume latest", suffix="resume_latest"), session.base_key, session)

    rebound = store.find_session(session.base_key)
    assert rebound is not None
    assert rebound.session_id == session.session_id
    assert rebound.native_session_id == "thread_latest"
    assert "session_id=thread_latest" in str(hooks.replies[-1]["text"])
    assert "已在当前顶层对话中连接；接下来直接继续发消息即可。" in str(hooks.replies[-1]["text"])
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_resume_local_session_id_maps_to_native_thread(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    original = store.load_session("p2p:oc_1")
    original.native_session_id = "thread_older"
    store.save_session(original)

    await router.handle(make_message(f"/resume {original.session_id}", suffix="resume_local"), original.base_key, original)

    rebound = store.find_session(original.base_key)
    assert rebound is not None
    assert rebound.session_id == original.session_id
    assert rebound.native_session_id == "thread_older"
    assert "session_id=thread_older" in str(hooks.replies[-1]["text"])
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_compact_current_native_thread(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")
    session.native_session_id = "thread_latest"
    store.save_session(session)

    await router.handle(make_message("/compact", suffix="compact"), session.base_key, session)

    assert hooks.replies[-1]["text"] == "codex compact 已完成：thread_latest\ncompact_id=compact_1"
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_opens_workspace_panel(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message("/workspace", suffix="workspace"), session.base_key, session)

    assert hooks.panel_calls[-1] == ("om_workspace", session.base_key, "workspace", 1, "updated-desc")
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_manages_directory_shortcuts(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    docs_dir = router.config.main_workspace_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message("/shortcut add docs docs main", suffix="shortcut_add"), session.base_key, session)
    await router.handle(make_message("/shortcut list", suffix="shortcut_list"), session.base_key, session)
    await router.handle(make_message("/shortcut use docs", suffix="shortcut_use"), session.base_key, session)
    await router.handle(make_message("/shortcut remove docs", suffix="shortcut_remove"), session.base_key, session)

    assert store.get_directory_shortcut("docs") is None
    assert hooks.replies[0]["text"].startswith("已保存快捷目录 `docs`。")
    assert "快捷目录：" in str(hooks.replies[1]["text"])
    assert "docs -> docs [main]" in str(hooks.replies[1]["text"])
    assert str(hooks.replies[2]["text"]).startswith("工作区已切换到 docs。")
    assert hooks.replies[3]["text"] == "已删除快捷目录 `docs`。"
    store.close()
