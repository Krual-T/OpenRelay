from pathlib import Path

import pytest

from tests.runtime.command_router_support import build_router, make_message


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
async def test_runtime_command_router_replies_panel_removed_and_admin_restart(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message("/help", suffix="help"), session.base_key, session)
    await router.handle(make_message("/panel", suffix="panel"), session.base_key, session)
    await router.handle(make_message("/restart", sender_open_id="ou_admin", suffix="restart_admin"), session.base_key, session)

    assert hooks.help_calls == [("om_help", session.base_key, ("claude", "codex"))]
    assert hooks.panel_calls == []
    assert hooks.replies[-2]["text"] == "`/panel` 已移除；恢复历史会话请用 `/resume`，切工作区请用 `/workspace`，查看现场请用 `/status`。"
    assert hooks.restart_scheduled == 1
    assert hooks.replies[-1]["text"] == "正在重启 openrelay，预计几秒后恢复。"
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
