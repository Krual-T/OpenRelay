from pathlib import Path

import pytest

from openrelay.session import SESSION_SORT_ACTIVE
from tests.runtime.command_router_support import build_router, make_card_action_message, make_message, make_thread_message


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

    assert hooks.session_list_calls == [(session.base_key, 3, "updated-desc")]
    assert hooks.replies == []
    assert hooks.panel_calls == []
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
