from pathlib import Path

import pytest

from openrelay.config import AppConfig, BackendConfig, FeishuConfig
from openrelay.models import IncomingMessage
from openrelay.runtime import HelpRenderer
from openrelay.runtime import RuntimeCommandHooks, RuntimeCommandRouter
from openrelay.session import SESSION_SORT_ACTIVE, SessionBrowser, SessionUX
from openrelay.state import StateStore


class FakeHooks:
    def __init__(self) -> None:
        self.replies: list[dict[str, object]] = []
        self.help_calls: list[tuple[str, str]] = []
        self.panel_calls: list[tuple[str, str, str, int, str]] = []
        self.session_list_calls: list[tuple[str, int, str]] = []
        self.switch_calls: list[tuple[str, str, str]] = []
        self.stop_calls: list[str] = []
        self.restart_scheduled = 0

    async def reply(self, message: IncomingMessage, text: str, **kwargs) -> None:
        self.replies.append({"message": message, "text": text, "kwargs": kwargs})

    async def send_help(self, message: IncomingMessage, session_key: str, session) -> None:
        self.help_calls.append((message.message_id, session_key))

    async def send_panel(self, message: IncomingMessage, session_key: str, session, args) -> None:
        self.panel_calls.append((message.message_id, session_key, args.view, args.page, args.sort_mode))

    async def send_session_list(self, message: IncomingMessage, session_key: str, session, page: int, sort_mode: str) -> None:
        self.session_list_calls.append((session_key, page, sort_mode))

    async def switch_release_channel(self, message: IncomingMessage, session_key: str, session, target_channel: str, command_name: str, reason: str) -> None:
        self.switch_calls.append((session_key, target_channel, command_name))

    async def stop(self, message: IncomingMessage, session_key: str) -> None:
        self.stop_calls.append(session_key)

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



def build_router(tmp_path: Path) -> tuple[RuntimeCommandRouter, StateStore, FakeHooks]:
    config = make_config(tmp_path)
    prepare_dirs(config)
    store = StateStore(config)
    session_ux = SessionUX(config, store)
    browser = SessionBrowser(config, store)
    hooks = FakeHooks()
    router = RuntimeCommandRouter(
        config,
        store,
        browser,
        session_ux,
        HelpRenderer(config, store, session_ux),
        {"codex": object(), "claude": object()},
        RuntimeCommandHooks(
            reply=hooks.reply,
            send_help=hooks.send_help,
            send_panel=hooks.send_panel,
            send_session_list=hooks.send_session_list,
            switch_release_channel=hooks.switch_release_channel,
            stop=hooks.stop,
            schedule_restart=hooks.schedule_restart,
            is_admin=hooks.is_admin,
            available_backend_names=hooks.available_backend_names,
        ),
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

    assert hooks.help_calls == [("om_help", session.base_key)]
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
async def test_runtime_command_router_parses_resume_list_page_and_sort(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message(f"/resume list --page 2 --sort {SESSION_SORT_ACTIVE}", suffix="resume_list"), session.base_key, session)

    assert hooks.session_list_calls == [(session.base_key, 2, SESSION_SORT_ACTIVE)]
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_parses_equals_style_paging_args(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message("/resume list --page=3 --sort=updated-desc", suffix="resume_equals"), session.base_key, session)
    await router.handle(make_message("/panel --page=2 --sort=active-first", suffix="panel_equals"), session.base_key, session)

    assert hooks.session_list_calls == [(session.base_key, 3, "updated-desc")]
    assert hooks.panel_calls == [("om_panel_equals", session.base_key, "sessions", 2, "active-first")]
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_rejects_resume_inside_thread(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    handled = await router.handle(make_thread_message("/resume list", suffix="thread_resume"), session.base_key, session)

    assert handled is True
    assert hooks.session_list_calls == []
    assert hooks.replies[-1]["text"] == "`/resume` 只允许在私聊顶层使用；子 thread 会固定绑定当前 Codex 会话。"
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_new_binds_current_top_level_thread_scope(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message("/new bugfix", suffix="new_scope"), session.base_key, session)

    scoped = store.find_session("p2p:oc_1:thread:om_new_scope")
    assert scoped is not None
    assert scoped.session_id != session.session_id
    assert hooks.replies[-1]["text"].startswith("已新建会话 ")
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_rejects_new_inside_thread(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    handled = await router.handle(make_thread_message("/new bugfix", suffix="thread_new"), session.base_key, session)

    assert handled is True
    assert hooks.replies[-1]["text"] == "`/new` 只允许在私聊顶层使用；子 thread 会固定绑定当前 Codex 会话。"
    assert store.find_session("p2p:oc_1:thread:om_thread_new") is None
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_manages_directory_shortcuts(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    docs_dir = router.config.main_workspace_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message("/shortcut add docs docs main", suffix="shortcut_add"), session.base_key, session)
    await router.handle(make_message("/shortcut list", suffix="shortcut_list"), session.base_key, session)
    await router.handle(make_message("/shortcut cd docs", suffix="shortcut_cd"), session.base_key, session)
    await router.handle(make_message("/shortcut remove docs", suffix="shortcut_remove"), session.base_key, session)

    assert store.get_directory_shortcut("docs") is None
    assert hooks.replies[0]["text"].startswith("已保存快捷目录 `docs`。")
    assert "快捷目录：" in str(hooks.replies[1]["text"])
    assert "docs -> docs [main]" in str(hooks.replies[1]["text"])
    assert str(hooks.replies[2]["text"]).startswith("cwd 已切换到 docs。")
    assert hooks.replies[3]["text"] == "已删除快捷目录 `docs`。"
    store.close()
