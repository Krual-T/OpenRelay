from pathlib import Path
import os
import signal

import pytest

from openrelay.backends.base import Backend, BackendContext
from openrelay.config import AppConfig, BackendConfig, FeishuConfig
from openrelay.models import BackendReply, IncomingMessage, SessionRecord
from openrelay.runtime import AgentRuntime, is_systemd_service_process
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


def test_is_systemd_service_process_detects_service_env() -> None:
    assert is_systemd_service_process({}) is False
    assert is_systemd_service_process({"INVOCATION_ID": "abc"}) is True
    assert is_systemd_service_process({"SYSTEMD_EXEC_PID": "1"}) is True
    assert is_systemd_service_process({"JOURNAL_STREAM": "9:9"}) is True


@pytest.mark.asyncio
async def test_runtime_restart_process_execs_outside_systemd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = make_config(tmp_path)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": FakeBackend()})

    async def fake_sleep(_seconds: float) -> None:
        return None

    exec_calls: list[tuple[str, list[str], dict[str, str]]] = []

    def fake_execvpe(file: str, argv: list[str], env: dict[str, str]) -> None:
        exec_calls.append((file, argv, env))

    monkeypatch.setattr("openrelay.runtime.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("openrelay.runtime.is_systemd_service_process", lambda env=None: False)
    monkeypatch.setattr("openrelay.runtime.os.execvpe", fake_execvpe)

    await runtime._restart_process()

    assert exec_calls
    assert exec_calls[0][0]
    assert exec_calls[0][1][-2:] == ["-m", "openrelay"]
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_restart_process_uses_sigterm_under_systemd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = make_config(tmp_path)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = AgentRuntime(config, store, messenger, backends={"codex": FakeBackend()})

    async def fake_sleep(_seconds: float) -> None:
        return None

    kill_calls: list[tuple[int, signal.Signals]] = []

    def fake_kill(pid: int, sig: signal.Signals) -> None:
        kill_calls.append((pid, sig))

    def fake_execvpe(_file: str, _argv: list[str], _env: dict[str, str]) -> None:
        raise AssertionError("execvpe should not be called under systemd")

    monkeypatch.setattr("openrelay.runtime.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("openrelay.runtime.is_systemd_service_process", lambda env=None: True)
    monkeypatch.setattr("openrelay.runtime.os.kill", fake_kill)
    monkeypatch.setattr("openrelay.runtime.os.execvpe", fake_execvpe)

    await runtime._restart_process()

    assert kill_calls == [(os.getpid(), signal.SIGTERM)]
    await runtime.shutdown()
