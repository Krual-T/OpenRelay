from pathlib import Path

import pytest

from tests.support.runtime_command_router import build_router, make_message, make_thread_message


@pytest.mark.asyncio
async def test_runtime_command_router_opens_workspace_browser(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message("/workspace", suffix="workspace"), session.base_key, session)

    assert hooks.panel_calls[-1] == ("om_workspace", session.base_key, "workspace", 1, "updated-desc")
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_rejects_workspace_inside_thread(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    handled = await router.handle(make_thread_message("/workspace", suffix="thread_workspace"), session.base_key, session)

    assert handled is True
    assert hooks.panel_calls == []
    assert hooks.replies[-1]["text"] == "`/workspace` 只允许在私聊顶层使用；子 thread 不应改工作区。"
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_supports_workspace_open_and_query(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    target = router.config.main_workspace_dir / "docs"
    target.mkdir(parents=True, exist_ok=True)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message('/workspace open docs --query api', suffix='workspace_open'), session.base_key, session)

    assert hooks.panel_calls[-1] == ("om_workspace_open", session.base_key, "workspace", 1, "updated-desc")
    store.close()


@pytest.mark.asyncio
async def test_runtime_command_router_supports_workspace_hidden_flag(tmp_path: Path) -> None:
    router, store, hooks = build_router(tmp_path)
    session = store.load_session("p2p:oc_1")

    await router.handle(make_message("/workspace --hidden", suffix="workspace_hidden"), session.base_key, session)

    assert hooks.panel_calls[-1] == ("om_workspace_hidden", session.base_key, "workspace", 1, "updated-desc")
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
    assert str(hooks.replies[1]["text"]).startswith("快捷目录：\n- docs -> ")
    assert str(hooks.replies[2]["text"]).startswith("工作区已切换到 docs。")
    assert hooks.replies[3]["text"] == "已删除快捷目录 `docs`。"
    store.close()
