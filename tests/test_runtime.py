import asyncio
import shlex
from pathlib import Path
import os

import pytest

from openrelay.backends.base import Backend, BackendContext
from openrelay.config import AppConfig, BackendConfig, DirectoryShortcut, FeishuConfig
from openrelay.feishu import parse_card_action_event
from openrelay.follow_up import MERGED_FOLLOW_UP_INTRO
from openrelay.models import BackendReply, IncomingMessage, SessionRecord
from openrelay.runtime import AgentRuntime, get_systemd_service_unit, is_systemd_service_process
from openrelay.session_ux import SessionUX
from openrelay.state import StateStore


class FakeMessenger:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.cards: list[dict] = []
        self.text_calls: list[dict] = []

    async def send_text(self, chat_id: str, text: str, *, reply_to_message_id: str = "", root_id: str = "", force_new_message: bool = False) -> None:
        self.messages.append(text)
        self.text_calls.append({"chat_id": chat_id, "text": text, "reply_to_message_id": reply_to_message_id, "root_id": root_id, "force_new_message": force_new_message})

    async def send_interactive_card(self, chat_id: str, card: dict, *, reply_to_message_id: str = "", root_id: str = "", force_new_message: bool = False) -> None:
        self.cards.append(card)

    async def close(self) -> None:
        return None


def extract_card_commands(card: dict) -> list[str]:
    commands: list[str] = []
    for element in card.get("elements", []):
        if element.get("tag") != "action":
            continue
        for action in element.get("actions", []):
            value = action.get("value") if isinstance(action, dict) else None
            if isinstance(value, dict) and value.get("command"):
                commands.append(str(value["command"]))
    return commands


def extract_card_text(card: dict) -> str:
    contents: list[str] = []
    for element in card.get("elements", []):
        if not isinstance(element, dict):
            continue
        text = element.get("text")
        if isinstance(text, dict) and isinstance(text.get("content"), str):
            contents.append(text["content"])
    return "\n".join(contents)


def find_card_action_value(card: dict, command: str) -> dict:
    for element in card.get("elements", []):
        if element.get("tag") != "action":
            continue
        for action in element.get("actions", []):
            value = action.get("value") if isinstance(action, dict) else None
            if isinstance(value, dict) and value.get("command") == command:
                return value
    raise AssertionError(f"command not found in card: {command}")


class FakeBackend(Backend):
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[tuple[SessionRecord, str]] = []

    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        self.calls.append((session, prompt))
        return BackendReply(text=f"echo: {prompt}", native_session_id="native_1", metadata={"usage": {"input_tokens": 100, "cached_input_tokens": 50, "output_tokens": 20, "total_tokens": 170, "model_context_window": 1000}})


class FakeStreamingSession:
    def __init__(self, messenger):
        self.started = False
        self.closed = False
        self.updates = []
        self.final_text = None

    async def start(self, receive_id: str, *, reply_to_message_id: str = "", root_id: str = "") -> None:
        self.started = True

    async def update(self, live_state: dict) -> None:
        self.updates.append(dict(live_state))

    async def close(self, final_text: str | None) -> None:
        self.closed = True
        self.final_text = final_text

    def has_started(self) -> bool:
        return self.started

    def is_active(self) -> bool:
        return self.started and not self.closed


class FakeTypingManager:
    def __init__(self):
        self.added = []
        self.removed = []

    async def add(self, message_id: str):
        self.added.append(message_id)
        return {"message_id": message_id, "reaction_id": "r1"}

    async def remove(self, state):
        self.removed.append(state)


class ProgressBackend(Backend):
    name = "fake"

    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        if context.on_progress is not None:
            await context.on_progress({"type": "run.started"})
        if context.on_partial_text is not None:
            await context.on_partial_text(f"partial: {prompt}")
        if context.on_progress is not None:
            await context.on_progress({"type": "assistant.partial", "text": f"partial: {prompt}"})
        return BackendReply(text=f"done: {prompt}", native_session_id="native_2")


class InterruptibleBackend(Backend):
    name = "fake"

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        self.started.set()
        if context.cancel_event is None:
            raise AssertionError("cancel_event is required for interruptible backend test")
        await context.cancel_event.wait()
        self.cancelled.set()
        raise RuntimeError("interrupted by /stop")


class QueuedFollowUpBackend(Backend):
    name = "fake"

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.first_started = asyncio.Event()
        self.release_first = asyncio.Event()

    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            self.first_started.set()
            await self.release_first.wait()
        return BackendReply(text=f"done: {prompt}", native_session_id=f"native_{len(self.prompts)}")


class StopThenContinueBackend(Backend):
    name = "fake"

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.first_started = asyncio.Event()

    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            self.first_started.set()
            if context.cancel_event is None:
                raise AssertionError("cancel_event is required for stop-follow-up test")
            await context.cancel_event.wait()
            raise RuntimeError("interrupted by /stop")
        return BackendReply(text=f"done: {prompt}", native_session_id="native_follow_up")


class BlockingStreamingSession(FakeStreamingSession):
    def __init__(self, messenger):
        super().__init__(messenger)
        self.update_calls = 0

    async def update(self, live_state: dict) -> None:
        self.update_calls += 1
        self.updates.append(dict(live_state))
        if self.update_calls > 1:
            await asyncio.Event().wait()



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
        feishu=FeishuConfig(
            app_id="app",
            app_secret="secret",
            verify_token="verify-token",
            bot_open_id="ou_bot",
            allowed_open_ids={"ou_user"},
            admin_open_ids={"ou_admin"},
        ),
        backend=BackendConfig(default_backend="codex", default_safety_mode="workspace-write", codex_sessions_dir=tmp_path / "native"),
    )



def make_message(text: str, sender_open_id: str = "ou_user", event_suffix: str = "") -> IncomingMessage:
    suffix = event_suffix or text
    return IncomingMessage(
        event_id=f"evt_{suffix}",
        message_id=f"om_{suffix}",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id=sender_open_id,
        text=text,
        actionable=True,
    )


@pytest.mark.asyncio
async def test_runtime_runs_backend_turn(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = FakeBackend()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": backend})

    await runtime.dispatch_message(make_message("hello"))

    assert backend.calls
    assert messenger.messages[-1] == "echo: hello"
    session = store.load_session(runtime.build_session_key(make_message("hello")))
    assert session.native_session_id == "native_1"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_blocks_unauthorized_sender(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = FakeBackend()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": backend})

    await runtime.dispatch_message(make_message("hello", sender_open_id="ou_other"))

    assert not backend.calls
    assert messenger.messages[-1] == "你没有权限使用 openrelay。"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_panel_command_sends_card(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": FakeBackend()})

    await runtime.dispatch_message(make_message("/panel"))
    assert messenger.cards
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_panel_shortcuts_switch_cwd_from_button(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    main_docs = config.main_workspace_dir / "docs"
    main_shared = config.main_workspace_dir / "shared"
    develop_shared = config.develop_workspace_dir / "shared"
    develop_api = config.develop_workspace_dir / "api"
    for path in [main_docs, main_shared, develop_shared, develop_api]:
        path.mkdir(parents=True, exist_ok=True)
    config.directory_shortcuts = (
        DirectoryShortcut(name="文档", path="docs", channels=("main",)),
        DirectoryShortcut(name="共享", path="shared", channels=("all",)),
        DirectoryShortcut(name="修复 API", path="api", channels=("develop",)),
    )
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": FakeBackend()})

    await runtime.dispatch_message(make_message("/panel", event_suffix="panel_shortcuts_main"))

    main_card = messenger.cards[-1]
    main_commands = extract_card_commands(main_card)
    docs_command = f"/cwd {shlex.quote(str(main_docs))}"
    main_shared_command = f"/cwd {shlex.quote(str(main_shared))}"
    develop_command = f"/cwd {shlex.quote(str(develop_api))}"
    assert docs_command in main_commands
    assert main_shared_command in main_commands
    assert develop_command not in main_commands

    docs_action = find_card_action_value(main_card, docs_command)
    parsed = parse_card_action_event(
        {
            "token": "tok_panel_docs",
            "operator": {"open_id": "ou_user"},
            "action": {"value": docs_action},
            "context": {"open_chat_id": "oc_1", "open_message_id": "om_panel_docs"},
        }
    )
    assert parsed.message is not None
    await runtime.dispatch_message(parsed.message)
    session = store.load_session(runtime.build_session_key(make_message("x")))
    assert session.cwd == str(main_docs)

    await runtime.dispatch_message(make_message("/develop bugfix", event_suffix="panel_shortcuts_develop_switch"))
    await runtime.dispatch_message(make_message("/panel", event_suffix="panel_shortcuts_develop"))
    develop_card = messenger.cards[-1]
    develop_commands = extract_card_commands(develop_card)
    develop_shared_command = f"/cwd {shlex.quote(str(develop_shared))}"
    assert docs_command not in develop_commands
    assert develop_shared_command in develop_commands
    assert develop_command in develop_commands

    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_resume_list_sends_paginated_sortable_card(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": FakeBackend()})

    older = store.load_session("p2p:oc_1")
    older.label = "older"
    older.native_session_id = "native_old"
    store.save_session(older)
    for index in range(6):
        next_session = store.create_next_session(older.base_key, older, f"session-{index}")
        next_session.native_session_id = f"native_{index}"
        store.save_session(next_session)

    await runtime.dispatch_message(make_message("/resume list", event_suffix="resume_list"))

    assert messenger.cards
    commands = extract_card_commands(messenger.cards[-1])
    assert any(command.startswith("/resume s_") for command in commands)
    assert "/resume list --page 2 --sort updated-desc" in commands
    assert "/resume list --page 1 --sort active-first" in commands

    await runtime.dispatch_message(make_message("/resume list --page 2 --sort active-first", event_suffix="resume_page2"))
    latest_card = messenger.cards[-1]
    header_text = latest_card["elements"][0]["text"]["content"]
    assert "第 `2` 页" in header_text
    assert "当前会话优先" in header_text

    await runtime.dispatch_message(make_message(f"/resume {older.session_id}", event_suffix="resume_old"))
    assert messenger.messages[-1].startswith("已恢复会话：older")
    assert f"session_id={older.session_id}" in messenger.messages[-1]
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_help_command_shows_actionable_guidance(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": FakeBackend()})

    await runtime.dispatch_message(make_message("/help", event_suffix="help0"))
    assert messenger.cards
    empty_card = messenger.cards[-1]
    assert empty_card["header"]["title"]["content"] == "openrelay help"
    empty_help = extract_card_text(empty_card)
    assert "当前状态" in empty_help
    assert "会话阶段：未开始（还没发第一条真实需求）" in empty_help
    assert "原生会话：`pending`" in empty_help
    assert "一句话判断：这是一个空会话；最有效的动作通常是直接发完整任务，而不是先试很多命令。" in empty_help
    assert "这是一个空会话；最有效的动作通常是直接发完整任务，而不是先试很多命令。" in empty_help
    assert "你现在最该做什么" in empty_help
    assert "先把目标说完整：要改什么、在哪个目录、是否要直接改代码。" in empty_help
    assert "下一条消息可以直接这样发" in empty_help
    assert "在 <path> 下实现 <需求>；先列计划，再按最小改动完成。" in empty_help
    assert "什么时候该用命令" in empty_help
    assert "/status 看会话、目录、最近上下文；/usage 看 token 和 context_usage。" in empty_help
    assert "最近关注：还没有可总结的本地上下文" in empty_help
    empty_commands = extract_card_commands(empty_card)
    assert "/status" in empty_commands
    assert "/usage" in empty_commands
    assert "/resume list" in empty_commands
    assert "/new" in empty_commands
    assert "/cwd" in empty_commands
    assert "/main" in empty_commands
    assert "/develop" in empty_commands

    status_action = find_card_action_value(empty_card, "/status")
    parsed = parse_card_action_event(
        {
            "token": "tok_help_status",
            "operator": {"open_id": "ou_user"},
            "action": {"value": status_action},
            "context": {"open_chat_id": "oc_1", "open_message_id": "om_help_card"},
        }
    )
    assert parsed.message is not None
    assert parsed.message.session_key == runtime.build_session_key(make_message("/help", event_suffix="help0"))

    await runtime.dispatch_message(parsed.message)
    assert messenger.messages[-1].startswith("session_base=p2p:oc_1")

    await runtime.dispatch_message(make_message("hello help", event_suffix="help1"))
    await runtime.dispatch_message(make_message("/help", event_suffix="help2"))

    help_card = messenger.cards[-1]
    help_text = extract_card_text(help_card)
    assert "会话阶段：进行中（继续发消息会沿用当前原生会话）" in help_text
    assert "上下文占用：`17.0% (170/1000)`" in help_text
    assert "最近关注：用户：hello help | 助手：echo: hello help" in help_text
    assert "这是一个进行中的会话；如果任务没变，直接补充信息最快。" in help_text
    assert "如果还是同一件事，直接追加信息：目标、报错、文件路径、验收标准。" in help_text
    assert "当前回复还没结束时，继续发消息会自动排到下一轮；连续补充会合并处理。" in help_text
    assert "基于现在的进度继续，不要重来；做完告诉我改了哪些文件。" in help_text
    assert "同一任务继续干：通常不用命令，直接发消息。" in help_text
    assert "当前回复还在跑时，继续发消息会进入下一轮；连续补充会自动合并。" in help_text
    assert "/stop" in extract_card_commands(help_card)
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_main_switch_creates_release_session(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": FakeBackend()})

    await runtime.dispatch_message(make_message("/develop bugfix", sender_open_id="ou_user", event_suffix="dev"))
    await runtime.dispatch_message(make_message("/main restore", sender_open_id="ou_user", event_suffix="main"))

    session = store.load_session(runtime.build_session_key(make_message("x")))
    assert session.release_channel == "main"
    assert session.safety_mode == "read-only"
    assert "已强制切到 main 稳定版本。" in messenger.messages[-1]
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_sandbox_command_requires_admin_for_danger(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": FakeBackend()})

    await runtime.dispatch_message(make_message("/sandbox danger-full-access"))
    assert messenger.messages[-1] == "danger-full-access 只允许管理员切换。"

    await runtime.dispatch_message(make_message("/sandbox danger-full-access", sender_open_id="ou_admin", event_suffix="admin"))
    assert messenger.messages[-1] == "sandbox 已切换到 danger-full-access，新的原生会话会在首条真实消息时创建。"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_card_stream_mode_uses_streaming_session(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.feishu.stream_mode = "card"
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    typing = FakeTypingManager()
    sessions: list[FakeStreamingSession] = []

    def factory(current_messenger):
        session = FakeStreamingSession(current_messenger)
        sessions.append(session)
        return session

    runtime = AgentRuntime(
        config,
        store,
        messenger,
        backends={"codex": FakeBackend()},
        streaming_session_factory=factory,
        typing_manager=typing,
    )

    await runtime.dispatch_message(make_message("hello stream", event_suffix="stream"))

    assert sessions
    assert sessions[0].started is True
    assert sessions[0].closed is True
    assert sessions[0].final_text == "echo: hello stream"
    assert typing.added == ["om_stream"]
    assert typing.removed
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_streaming_update_does_not_block_backend_turn(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.feishu.stream_mode = "card"
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    typing = FakeTypingManager()
    sessions: list[BlockingStreamingSession] = []

    def factory(current_messenger):
        session = BlockingStreamingSession(current_messenger)
        sessions.append(session)
        return session

    runtime = AgentRuntime(
        config,
        store,
        messenger,
        backends={"codex": ProgressBackend()},
        streaming_session_factory=factory,
        typing_manager=typing,
    )

    await asyncio.wait_for(runtime.dispatch_message(make_message("hello blocked stream", event_suffix="blocked_stream")), timeout=1)

    assert sessions
    assert sessions[0].started is True
    assert sessions[0].closed is True
    assert sessions[0].final_text == "done: hello blocked stream"
    session = store.load_session(runtime.build_session_key(make_message("hello blocked stream", event_suffix="blocked_stream")))
    assert session.native_session_id == "native_2"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_stop_interrupts_active_run(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = InterruptibleBackend()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": backend})

    run_task = asyncio.create_task(runtime.dispatch_message(make_message("long running", event_suffix="run")))
    await asyncio.wait_for(backend.started.wait(), timeout=1)

    await runtime.dispatch_message(make_message("/stop", event_suffix="stop"))
    await asyncio.wait_for(run_task, timeout=1)

    assert backend.cancelled.is_set() is True
    assert "已发送停止请求，正在中断当前回复。" in messenger.messages
    assert "已停止当前回复。" in messenger.messages
    assert len(runtime.active_runs) == 0
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_merges_follow_up_messages_during_active_run(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = QueuedFollowUpBackend()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": backend})

    run_task = asyncio.create_task(runtime.dispatch_message(make_message("first", event_suffix="first")))
    await asyncio.wait_for(backend.first_started.wait(), timeout=1)

    await runtime.dispatch_message(make_message("补充一", event_suffix="follow_1"))
    await runtime.dispatch_message(make_message("补充二", event_suffix="follow_2"))

    backend.release_first.set()
    await asyncio.wait_for(run_task, timeout=1)

    assert backend.prompts[0] == "first"
    assert MERGED_FOLLOW_UP_INTRO in backend.prompts[1]
    assert "补充消息 1：\n补充一" in backend.prompts[1]
    assert "补充消息 2：\n补充二" in backend.prompts[1]
    assert "已收到补充，会在当前回复结束后自动继续；后续新补充会合并到下一轮。" in messenger.messages
    assert "已收到补充，当前累计 2 条；当前回复结束后会合并成下一轮继续。" in messenger.messages
    assert messenger.messages[-1].startswith(f"done: {MERGED_FOLLOW_UP_INTRO}")
    assert len(runtime.active_runs) == 0
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_stop_keeps_queued_follow_up(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = StopThenContinueBackend()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": backend})

    run_task = asyncio.create_task(runtime.dispatch_message(make_message("long running", event_suffix="queued_run")))
    await asyncio.wait_for(backend.first_started.wait(), timeout=1)

    await runtime.dispatch_message(make_message("补充 stop", event_suffix="queued_follow_up"))
    await runtime.dispatch_message(make_message("/stop", event_suffix="queued_stop"))
    await asyncio.wait_for(run_task, timeout=1)

    assert backend.prompts == ["long running", "补充 stop"]
    assert "已收到补充，会在当前回复结束后自动继续；后续新补充会合并到下一轮。" in messenger.messages
    assert "已发送停止请求，正在中断当前回复 停止后会继续处理已收到的 1 条补充消息。" in messenger.messages
    assert "已停止当前回复。" in messenger.messages
    assert messenger.messages[-1] == "done: 补充 stop"
    assert len(runtime.active_runs) == 0
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_top_level_p2p_cwd_prefers_thread_reply(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    target = config.main_workspace_dir / "subdir"
    target.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": FakeBackend()})

    await runtime.dispatch_message(make_message("/cwd subdir", event_suffix="cwd"))

    assert messenger.text_calls[-1]["force_new_message"] is False
    assert messenger.text_calls[-1]["reply_to_message_id"] == "om_cwd"
    await runtime.shutdown()


def test_session_ux_resolve_cwd_expands_home_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    target = config.main_workspace_dir / "repo"
    target.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    session = store.load_session("p2p:oc_1")
    ux = SessionUX(config, store)

    resolved = ux.resolve_cwd(session.cwd, "~/main/repo", session)

    assert resolved == target.resolve()
    store.close()


def test_session_ux_resolve_cwd_rejects_missing_path(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    session = store.load_session("p2p:oc_1")
    ux = SessionUX(config, store)

    with pytest.raises(ValueError, match=r"path does not exist: missing-dir"):
        ux.resolve_cwd(session.cwd, "missing-dir", session)
    store.close()


def test_session_ux_resolve_cwd_rejects_file_path(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    file_path = config.main_workspace_dir / "README.md"
    file_path.write_text("demo", encoding="utf-8")
    store = StateStore(config)
    session = store.load_session("p2p:oc_1")
    ux = SessionUX(config, store)

    with pytest.raises(ValueError, match=r"not a directory: README\.md"):
        ux.resolve_cwd(session.cwd, "README.md", session)
    store.close()


@pytest.mark.asyncio
async def test_runtime_cwd_command_rejects_missing_path(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": FakeBackend()})

    await runtime.dispatch_message(make_message("/cwd missing-dir", event_suffix="cwd_missing"))

    session = store.load_session(runtime.build_session_key(make_message("x")))
    assert session.cwd == str(config.main_workspace_dir)
    assert messenger.messages[-1] == "cwd 切换失败：path does not exist: missing-dir"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_status_shows_recent_context(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": FakeBackend()})

    await runtime.dispatch_message(make_message("hello context", event_suffix="ctx1"))
    await runtime.dispatch_message(make_message("/status", event_suffix="ctx2"))

    assert "最近上下文：" in messenger.messages[-1]
    assert "用户：hello context" in messenger.messages[-1]
    assert "助手：echo: hello context" in messenger.messages[-1]
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_usage_command_shows_context_usage(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": FakeBackend()})

    await runtime.dispatch_message(make_message("hello usage", event_suffix="usage1"))
    await runtime.dispatch_message(make_message("/usage", event_suffix="usage2"))

    assert "context_usage=17.0% (170/1000)" in messenger.messages[-1]
    assert "usage_detail=in=100 cache=50 out=20 total=170 window=1000" in messenger.messages[-1]
    await runtime.shutdown()


def test_get_systemd_service_unit_prefers_override() -> None:
    assert get_systemd_service_unit({}) == "openrelay.service"
    assert get_systemd_service_unit({"OPENRELAY_SYSTEMD_UNIT": "custom.service"}) == "custom.service"


def test_is_systemd_service_process_requires_matching_exec_pid() -> None:
    current_pid = os.getpid()
    assert is_systemd_service_process({}) is False
    assert is_systemd_service_process({"INVOCATION_ID": "abc"}) is False
    assert is_systemd_service_process({"JOURNAL_STREAM": "9:9"}) is False
    assert is_systemd_service_process({"SYSTEMD_EXEC_PID": str(current_pid)}) is True
    assert is_systemd_service_process({"SYSTEMD_EXEC_PID": str(current_pid + 1)}) is False


@pytest.mark.asyncio
async def test_runtime_restart_process_uses_systemd_restart_when_service_managed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = make_config(tmp_path)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": FakeBackend()})

    async def fake_sleep(_seconds: float) -> None:
        return None

    systemd_calls: list[str] = []
    shutdown_calls: list[str] = []

    async def fake_restart_systemd_service(unit_name: str) -> None:
        systemd_calls.append(unit_name)

    async def fake_shutdown_all() -> None:
        shutdown_calls.append("shutdown")

    def fake_execvpe(_file: str, _argv: list[str], _env: dict[str, str]) -> None:
        raise AssertionError("execvpe should not be called for systemd-managed restart")

    monkeypatch.setattr("openrelay.runtime.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("openrelay.runtime.is_systemd_service_process", lambda env=None, pid=None: True)
    monkeypatch.setattr(runtime, "_restart_systemd_service", fake_restart_systemd_service)
    monkeypatch.setattr("openrelay.runtime.CodexBackend.shutdown_all", fake_shutdown_all)
    monkeypatch.setattr("openrelay.runtime.os.execvpe", fake_execvpe)

    await runtime._restart_process()

    assert systemd_calls == ["openrelay.service"]
    assert shutdown_calls == []
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_restart_process_execs_and_shuts_down_backends(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = make_config(tmp_path)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": FakeBackend()})

    async def fake_sleep(_seconds: float) -> None:
        return None

    exec_calls: list[tuple[str, list[str], dict[str, str]]] = []
    shutdown_calls: list[str] = []

    def fake_execvpe(file: str, argv: list[str], env: dict[str, str]) -> None:
        exec_calls.append((file, argv, env))

    async def fake_shutdown_all() -> None:
        shutdown_calls.append("shutdown")

    async def fake_restart_systemd_service(_unit_name: str) -> None:
        raise AssertionError("systemd restart should not be used outside service-managed mode")

    monkeypatch.setattr("openrelay.runtime.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("openrelay.runtime.is_systemd_service_process", lambda env=None, pid=None: False)
    monkeypatch.setattr(runtime, "_restart_systemd_service", fake_restart_systemd_service)
    monkeypatch.setattr("openrelay.runtime.os.execvpe", fake_execvpe)
    monkeypatch.setattr("openrelay.runtime.CodexBackend.shutdown_all", fake_shutdown_all)

    await runtime._restart_process()

    assert shutdown_calls == ["shutdown"]
    assert exec_calls
    assert exec_calls[0][0]
    assert exec_calls[0][1][-2:] == ["-m", "openrelay"]
    await runtime.shutdown()
