import asyncio
import shlex
from pathlib import Path
import os

import pytest

from openrelay.backends.base import Backend, BackendContext
from openrelay.core import AppConfig, BackendConfig, DirectoryShortcut, FeishuConfig
from openrelay.feishu import SentMessageRef, parse_card_action_event
from openrelay.presentation.session import SessionPresentation
from openrelay.runtime import MERGED_FOLLOW_UP_INTRO
from openrelay.core import BackendReply, IncomingMessage, SessionRecord
from openrelay.runtime import RuntimeOrchestrator, DEFAULT_IMAGE_PROMPT, get_systemd_service_unit, is_systemd_service_process
from openrelay.session import SessionWorkspaceService
from openrelay.storage import StateStore


class FakeMessenger:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.cards: list[dict] = []
        self.text_calls: list[dict] = []
        self.card_calls: list[dict] = []
        self._next_message_id = 1

    def _allocate_message_id(self) -> str:
        message_id = f"om_bot_{self._next_message_id}"
        self._next_message_id += 1
        return message_id

    async def send_text(self, chat_id: str, text: str, *, reply_to_message_id: str = "", root_id: str = "", force_new_message: bool = False) -> tuple[SentMessageRef, ...]:
        self.messages.append(text)
        message_id = self._allocate_message_id()
        self.text_calls.append({"chat_id": chat_id, "text": text, "reply_to_message_id": reply_to_message_id, "root_id": root_id, "force_new_message": force_new_message})
        return (SentMessageRef(message_id=message_id),)

    async def send_interactive_card(
        self,
        chat_id: str,
        card: dict,
        *,
        reply_to_message_id: str = "",
        root_id: str = "",
        force_new_message: bool = False,
        update_message_id: str = "",
    ) -> SentMessageRef:
        self.cards.append(card)
        message_id = update_message_id or self._allocate_message_id()
        self.card_calls.append({
            "chat_id": chat_id,
            "card": card,
            "reply_to_message_id": reply_to_message_id,
            "root_id": root_id,
            "force_new_message": force_new_message,
            "update_message_id": update_message_id,
        })
        return SentMessageRef(message_id=message_id)

    async def close(self) -> None:
        return None


class ThreadAwareFakeMessenger(FakeMessenger):
    async def send_text(self, chat_id: str, text: str, *, reply_to_message_id: str = "", root_id: str = "", force_new_message: bool = False) -> tuple[SentMessageRef, ...]:
        sent_messages = await super().send_text(
            chat_id,
            text,
            reply_to_message_id=reply_to_message_id,
            root_id=root_id,
            force_new_message=force_new_message,
        )
        if reply_to_message_id == "om_root":
            return (SentMessageRef(message_id=sent_messages[0].message_id, root_id="om_root", thread_id="thread_fixed"),)
        return sent_messages


class FailingCardMessenger(FakeMessenger):
    async def send_interactive_card(
        self,
        chat_id: str,
        card: dict,
        *,
        reply_to_message_id: str = "",
        root_id: str = "",
        force_new_message: bool = False,
        update_message_id: str = "",
    ) -> SentMessageRef:
        _ = chat_id, card, reply_to_message_id, root_id, force_new_message, update_message_id
        raise RuntimeError("card unavailable")


def extract_card_commands(card: dict) -> list[str]:
    commands: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        if node.get("tag") == "action":
            for action in node.get("actions", []):
                value = action.get("value") if isinstance(action, dict) else None
                if isinstance(value, dict) and value.get("command"):
                    commands.append(str(value["command"]))
        for key in ("elements", "columns", "fields"):
            walk(node.get(key))

    walk(card.get("elements", []))
    return commands


def extract_card_text(card: dict) -> str:
    contents: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        text = node.get("text")
        if isinstance(text, dict) and isinstance(text.get("content"), str):
            contents.append(text["content"])
        if isinstance(node.get("content"), str) and node.get("tag") in {"lark_md", "plain_text", "markdown"}:
            contents.append(str(node["content"]))
        for key in ("elements", "columns", "fields"):
            walk(node.get(key))

    walk(card.get("elements", []))
    return "\n".join(contents)


def find_card_action_value(card: dict, command: str) -> dict:
    def walk(node: object) -> dict | None:
        if isinstance(node, list):
            for item in node:
                result = walk(item)
                if result is not None:
                    return result
            return None
        if not isinstance(node, dict):
            return None
        if node.get("tag") == "action":
            for action in node.get("actions", []):
                value = action.get("value") if isinstance(action, dict) else None
                if isinstance(value, dict) and value.get("command") == command:
                    return value
        for key in ("elements", "columns", "fields"):
            result = walk(node.get(key))
            if result is not None:
                return result
        return None

    matched = walk(card.get("elements", []))
    if matched is not None:
        return matched
    raise AssertionError(f"command not found in card: {command}")


class FakeBackend(Backend):
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[tuple[SessionRecord, str]] = []

    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        self.calls.append((session, prompt))
        return BackendReply(text=f"echo: {prompt}", native_session_id="native_1", metadata={"usage": {"input_tokens": 100, "cached_input_tokens": 50, "output_tokens": 20, "total_tokens": 170, "model_context_window": 1000}})


class NativeCommandBackend(FakeBackend):
    async def list_threads(self, session: SessionRecord, context: BackendContext, limit: int = 20):
        _ = session, context
        rows = []
        for index in range(1, limit + 1):
            thread_id = "native_old" if index == 1 else f"native_{index - 2}" if index <= 8 else f"native_extra_{index}"
            rows.append(
                type(
                    "ThreadSummary",
                    (),
                    {
                        "thread_id": thread_id,
                        "preview": f"preview {index}",
                        "cwd": str(context.workspace_root),
                        "updated_at": f"2026-03-{min(index, 28):02d}T10:00:00Z",
                        "status": "idle",
                        "name": f"thread {index}",
                    },
                )()
            )
        return rows, ""

    async def read_thread(self, session: SessionRecord, context: BackendContext, thread_id: str, *, include_turns: bool = True):
        _ = session, context, include_turns
        return type(
            "ThreadDetails",
            (),
            {
                "thread_id": thread_id,
                "preview": f"preview for {thread_id}",
                "cwd": str(context.workspace_root),
                "updated_at": "2026-03-15T10:00:00Z",
                "status": "idle",
                "name": f"name {thread_id}",
                "messages": (
                    type("Msg", (), {"role": "user", "text": f"user {thread_id}"})(),
                    type("Msg", (), {"role": "assistant", "text": f"assistant {thread_id}"})(),
                ),
            },
        )()

    async def compact_thread(self, session: SessionRecord, context: BackendContext, thread_id: str):
        _ = session, context, thread_id
        return {"compactId": "compact_1"}


class SequentialNativeBackend(Backend):
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[tuple[SessionRecord, str]] = []

    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        _ = context
        self.calls.append((session, prompt))
        return BackendReply(text=f"echo: {prompt}", native_session_id=f"native_{len(self.calls)}")


class FakeStreamingSession:
    def __init__(self, messenger):
        self.started = False
        self.closed = False
        self.rollover_needed = False
        self.updates = []
        self.final_card = None
        self._message_id = "om_stream_card"
        self.start_calls = []

    async def start(self, receive_id: str, *, reply_to_message_id: str = "", root_id: str = "") -> None:
        self.started = True
        self.start_calls.append(
            {
                "receive_id": receive_id,
                "reply_to_message_id": reply_to_message_id,
                "root_id": root_id,
            }
        )

    async def update(self, live_state: dict) -> None:
        self.updates.append(dict(live_state))

    async def close(self, final_card: dict | None = None) -> None:
        self.closed = True
        self.final_card = final_card

    def message_id(self) -> str:
        return self._message_id if self.started else ""

    def message_alias_ids(self) -> tuple[str, ...]:
        return (self._message_id,) if self.started else ()

    def has_started(self) -> bool:
        return self.started

    def is_active(self) -> bool:
        return self.started and not self.closed and not self.rollover_needed

    def needs_rollover(self) -> bool:
        return self.started and not self.closed and self.rollover_needed

    async def freeze(self, live_state: dict, *, notice_text: str = "") -> None:
        self.rollover_needed = True
        self.updates.append({"freeze_notice": notice_text, **dict(live_state)})


class FailingFinalCardStreamingSession(FakeStreamingSession):
    def __init__(self, messenger):
        super().__init__(messenger)
        self.close_calls: list[dict | None] = []

    async def close(self, final_card: dict | None = None) -> None:
        self.close_calls.append(final_card)
        if final_card is not None and len(self.close_calls) == 1:
            raise RuntimeError("final card update failed")
        await super().close(final_card)


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


class SlowProgressBackend(Backend):
    name = "fake"

    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        _ = session
        if context.on_progress is not None:
            await context.on_progress({"type": "run.started"})
        if context.on_partial_text is not None:
            await context.on_partial_text(f"partial: {prompt}")
        await asyncio.sleep(0.05)
        return BackendReply(text=f"done: {prompt}", native_session_id="native_slow_progress")


class ReasoningBackend(Backend):
    name = "fake"

    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        if context.on_progress is not None:
            await context.on_progress({"type": "run.started"})
            await context.on_progress({"type": "reasoning.started"})
            await context.on_progress({"type": "reasoning.delta", "text": "先检查 runtime。"})
            await context.on_progress({"type": "reasoning.completed", "text": "先检查 runtime。\n再收敛 card 渲染。"})
        return BackendReply(text=f"done: {prompt}", native_session_id="native_reasoning")


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


class ApprovalRequestBackend(Backend):
    name = "fake"

    def __init__(self) -> None:
        self.decision = ""
        self.started = asyncio.Event()

    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        _ = session, prompt
        if context.on_server_request is None:
            raise AssertionError("on_server_request is required")
        self.started.set()
        result = await context.on_server_request(
            "item/commandExecution/requestApproval",
            {
                "threadId": "thread_1",
                "turnId": "turn_1",
                "itemId": "item_1",
                "command": "pytest -q",
                "cwd": "/workspace",
                "reason": "Run tests before applying changes.",
            },
        )
        self.decision = str(result.get("decision") or "")
        return BackendReply(text=f"decision: {self.decision}", native_session_id="native_approval")


class ToolUserInputBackend(Backend):
    name = "fake"

    def __init__(self) -> None:
        self.answers: dict[str, object] | None = None
        self.started = asyncio.Event()

    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        _ = session, prompt
        if context.on_server_request is None:
            raise AssertionError("on_server_request is required")
        self.started.set()
        result = await context.on_server_request(
            "item/tool/requestUserInput",
            {
                "threadId": "thread_1",
                "turnId": "turn_1",
                "itemId": "item_2",
                "questions": [
                    {
                        "id": "deploy_env",
                        "header": "Deploy Env",
                        "question": "Which environment should I deploy to?",
                        "options": [
                            {"label": "staging", "description": "Safer validation first."},
                            {"label": "production", "description": "Ship it live."},
                        ],
                    }
                ],
            },
        )
        self.answers = result
        chosen = result.get("answers", {}).get("deploy_env", {}).get("answers", [""])[0]  # type: ignore[index,union-attr]
        return BackendReply(text=f"env: {chosen}", native_session_id="native_input")


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


class ThreadAwareNativeBackend(Backend):
    name = "codex"

    def __init__(self) -> None:
        self.calls: list[tuple[SessionRecord, str]] = []
        self.thread_ids_seen_in_callback: list[str] = []

    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        self.calls.append((session, prompt))
        if context.on_thread_started is None:
            raise AssertionError("on_thread_started is required")
        await context.on_thread_started("native_started_1")
        self.thread_ids_seen_in_callback.append(session.native_session_id)
        return BackendReply(text=f"done: {prompt}", native_session_id=session.native_session_id)


class BlockingStreamingSession(FakeStreamingSession):
    def __init__(self, messenger):
        super().__init__(messenger)
        self.update_calls = 0

    async def update(self, live_state: dict) -> None:
        self.update_calls += 1
        self.updates.append(dict(live_state))
        if self.update_calls > 1:
            await asyncio.Event().wait()


class RollingStreamingSession(FakeStreamingSession):
    def __init__(self, messenger, *, roll_over_after: int = 2):
        super().__init__(messenger)
        self.update_calls = 0
        self.roll_over_after = roll_over_after

    async def update(self, live_state: dict) -> None:
        self.update_calls += 1
        self.updates.append(dict(live_state))
        if self.roll_over_after > 0 and self.update_calls >= self.roll_over_after:
            self.rollover_needed = True


class ImmediateRolloverStreamingSession(FakeStreamingSession):
    async def start(self, receive_id: str, *, reply_to_message_id: str = "", root_id: str = "") -> None:
        await super().start(receive_id, reply_to_message_id=reply_to_message_id, root_id=root_id)
        self.rollover_needed = True


class NativeSessionConcurrencyBackend(Backend):
    name = "fake"

    def __init__(self) -> None:
        self.started: dict[str, asyncio.Event] = {}
        self.released: dict[str, asyncio.Event] = {}
        self.start_order: list[str] = []

    def _ensure_prompt(self, prompt: str) -> tuple[asyncio.Event, asyncio.Event]:
        if prompt not in self.started:
            self.started[prompt] = asyncio.Event()
            self.released[prompt] = asyncio.Event()
        return self.started[prompt], self.released[prompt]

    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        started, released = self._ensure_prompt(prompt)
        self.start_order.append(prompt)
        started.set()
        await released.wait()
        return BackendReply(text=f"done: {prompt}", native_session_id=session.native_session_id or f"native_{prompt}")


class ImageAwareBackend(Backend):
    name = "fake"

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.image_paths: list[tuple[str, ...]] = []

    async def run(self, session: SessionRecord, prompt: str, context: BackendContext) -> BackendReply:
        self.prompts.append(prompt)
        self.image_paths.append(context.local_image_paths)
        return BackendReply(text="done: image", native_session_id="native_image")



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
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    await runtime.dispatch_message(make_message("hello"))

    assert backend.calls
    assert messenger.messages[-1] == "echo: hello"
    session = store.load_session(runtime.session_scope.build_session_key(make_message("hello")))
    assert session.native_session_id == "native_1"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_top_level_messages_start_independent_sessions_by_default(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = SequentialNativeBackend()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    first_message = make_message("first task", event_suffix="root_a")
    second_message = make_message("second task", event_suffix="root_b")

    await runtime.dispatch_message(first_message)
    await runtime.dispatch_message(second_message)

    first_session = store.load_session(runtime.session_scope.build_session_key(first_message))
    second_session = store.load_session(runtime.session_scope.build_session_key(second_message))

    assert first_session.session_id != second_session.session_id
    assert first_session.native_session_id == "native_1"
    assert second_session.native_session_id == "native_2"
    assert backend.calls[0][0].native_session_id == ""
    assert backend.calls[1][0].native_session_id == ""
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
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

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
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": NativeCommandBackend()})

    await runtime.dispatch_message(make_message("/panel"))
    assert messenger.cards
    panel_card = messenger.cards[-1]
    panel_text = extract_card_text(panel_card)
    panel_commands = extract_card_commands(panel_card)
    assert "面板 · 总览" in panel_text
    assert "/panel sessions" in panel_commands
    assert "/panel directories" in panel_commands
    assert "/panel commands" in panel_commands
    assert "/panel status" in panel_commands
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_panel_command_falls_back_to_text_when_card_send_fails(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FailingCardMessenger()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": NativeCommandBackend()})

    await runtime.dispatch_message(make_message("/panel", event_suffix="panel_fallback"))

    assert messenger.messages
    assert "OpenRelay 面板" in messenger.messages[-1]
    assert "结果面：/panel sessions | /panel directories | /panel commands | /panel status" in messenger.messages[-1]
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
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": NativeCommandBackend()})

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
    await runtime.dispatch_message(make_message("check cwd", event_suffix="panel_docs_prompt"))
    assert runtime.backends["codex"].calls[-1][0].cwd == str(main_docs)

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
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": NativeCommandBackend()})

    older = store.load_session("p2p:oc_1")
    older.label = "older"
    older.native_session_id = "native_old"
    store.save_session(older)
    for index in range(12):
        next_session = store.create_next_session(older.base_key, older, f"session-{index}")
        next_session.native_session_id = f"native_{index}"
        store.save_session(next_session)

    await runtime.dispatch_message(make_message("/resume", event_suffix="resume_list"))

    assert messenger.cards
    first_card = messenger.cards[-1]
    first_text = extract_card_text(first_card)
    first_commands = extract_card_commands(first_card)
    assert "Codex 会话" in first_text
    assert "id=native_old" in first_text
    assert "/resume native_old" in first_commands
    assert messenger.card_calls[-1]["force_new_message"] is True

    resume_page_2 = parse_card_action_event(
        {
            "token": "tok_resume_page2",
            "operator": {"open_id": "ou_user"},
            "action": {"value": find_card_action_value(first_card, "/resume --page 2")},
            "context": {"open_chat_id": "oc_1", "open_message_id": "om_resume_card"},
        }
    )
    assert resume_page_2.message is not None

    await runtime.dispatch_message(resume_page_2.message)

    assert messenger.card_calls[-1]["update_message_id"] == "om_resume_card"
    assert "第 `2` 页" in extract_card_text(messenger.cards[-1])

    await runtime.dispatch_message(make_message(f"/resume {older.session_id}", event_suffix="resume_old"))
    assert messenger.messages[-1].startswith("已连接 Codex 会话：name native_old")
    assert "thread_id=native_old" in messenger.messages[-1]
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_panel_navigation_updates_same_card_for_card_actions(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": FakeBackend()})

    await runtime.dispatch_message(make_message("/panel", event_suffix="panel_nav_root"))
    home_card = messenger.cards[-1]

    to_sessions = parse_card_action_event(
        {
            "token": "tok_panel_sessions",
            "operator": {"open_id": "ou_user"},
            "action": {"value": find_card_action_value(home_card, "/panel sessions")},
            "context": {"open_chat_id": "oc_1", "open_message_id": "om_panel_nav"},
        }
    )
    assert to_sessions.message is not None

    await runtime.dispatch_message(to_sessions.message)

    assert messenger.card_calls[-1]["update_message_id"] == "om_panel_nav"
    assert "面板 · 会话" in extract_card_text(messenger.cards[-1])

    back_home = parse_card_action_event(
        {
            "token": "tok_panel_home",
            "operator": {"open_id": "ou_user"},
            "action": {"value": find_card_action_value(messenger.cards[-1], "/panel")},
            "context": {"open_chat_id": "oc_1", "open_message_id": "om_panel_nav"},
        }
    )
    assert back_home.message is not None

    await runtime.dispatch_message(back_home.message)

    assert messenger.card_calls[-1]["update_message_id"] == "om_panel_nav"
    assert "面板 · 总览" in extract_card_text(messenger.cards[-1])
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_help_card_action_updates_same_message_when_opening_panel(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": FakeBackend()})

    await runtime.dispatch_message(make_message("/help", event_suffix="help_panel_nav"))
    help_card = messenger.cards[-1]

    to_panel = parse_card_action_event(
        {
            "token": "tok_help_panel",
            "operator": {"open_id": "ou_user"},
            "action": {"value": find_card_action_value(help_card, "/panel")},
            "context": {"open_chat_id": "oc_1", "open_message_id": "om_help_panel"},
        }
    )
    assert to_panel.message is not None

    await runtime.dispatch_message(to_panel.message)

    assert messenger.card_calls[-1]["update_message_id"] == "om_help_panel"
    assert "面板 · 总览" in extract_card_text(messenger.cards[-1])
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_panel_views_show_structured_results(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    main_docs = config.main_workspace_dir / "docs"
    develop_api = config.develop_workspace_dir / "api"
    main_docs.mkdir(parents=True, exist_ok=True)
    develop_api.mkdir(parents=True, exist_ok=True)
    config.directory_shortcuts = (
        DirectoryShortcut(name="文档", path="docs", channels=("main",)),
        DirectoryShortcut(name="修复 API", path="api", channels=("develop",)),
    )
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": FakeBackend()})

    current = store.load_session("p2p:oc_1")
    current.label = "current"
    store.save_session(current)
    for index in range(6):
        next_session = store.create_next_session(current.base_key, current, f"session-{index}")
        next_session.native_session_id = f"native_{index}"
        store.save_session(next_session)

    await runtime.dispatch_message(make_message("/panel sessions --page 2 --sort active-first", event_suffix="panel_sessions"))
    session_card = messenger.cards[-1]
    session_text = extract_card_text(session_card)
    session_commands = extract_card_commands(session_card)
    assert "面板 · 会话" in session_text
    assert "/resume latest" in session_commands
    assert "/resume --page 2 --sort active-first" in session_commands
    assert "/panel sessions --page 1 --sort updated-desc" in session_commands
    assert any(command.startswith("/resume s_") for command in session_commands)

    await runtime.dispatch_message(make_message("/panel directories", event_suffix="panel_directories"))
    directories_card = messenger.cards[-1]
    directory_text = extract_card_text(directories_card)
    directory_commands = extract_card_commands(directories_card)
    assert "面板 · 目录" in directory_text
    assert f"/cwd {shlex.quote(str(main_docs))}" in directory_commands

    await runtime.dispatch_message(make_message("/panel commands", event_suffix="panel_commands"))
    commands_card = messenger.cards[-1]
    commands_text = extract_card_text(commands_card)
    commands_commands = extract_card_commands(commands_card)
    assert "面板 · 命令" in commands_text
    assert "/resume latest" in commands_commands
    assert "/panel directories" in commands_commands
    assert "/help" in commands_commands

    await runtime.dispatch_message(make_message("/panel status", event_suffix="panel_status"))
    status_card = messenger.cards[-1]
    status_text = extract_card_text(status_card)
    status_commands = extract_card_commands(status_card)
    assert "面板 · 状态" in status_text
    assert "/status" in status_commands
    assert "/usage" in status_commands
    assert "/help" in status_commands

    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_help_command_shows_actionable_guidance(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": FakeBackend()})

    await runtime.dispatch_message(make_message("/help", event_suffix="help0"))
    assert messenger.cards
    empty_card = messenger.cards[-1]
    assert empty_card["header"]["title"]["content"] == "openrelay help"
    empty_help = extract_card_text(empty_card)
    assert "当前状态" in empty_help
    assert "阶段" in empty_help
    assert "未开始（还没发第一条真实需求）" in empty_help
    assert "pending" in empty_help
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
    assert "/resume" in empty_commands
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
    assert parsed.message.session_key == runtime.session_scope.build_session_key(make_message("/help", event_suffix="help0"))

    await runtime.dispatch_message(parsed.message)
    assert messenger.messages[-1].startswith("session_base=p2p:oc_1")

    await runtime.dispatch_message(make_message("hello help", event_suffix="help1"))
    await runtime.dispatch_message(make_message("/help", event_suffix="help2"))

    help_card = messenger.cards[-1]
    help_text = extract_card_text(help_card)
    assert "进行中（继续发消息会沿用当前后端线程）" in help_text
    assert "17.0% (170/1000)" in help_text
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
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": FakeBackend()})

    await runtime.dispatch_message(make_message("/develop bugfix", sender_open_id="ou_user", event_suffix="dev"))
    await runtime.dispatch_message(make_message("/main restore", sender_open_id="ou_user", event_suffix="main"))
    await runtime.dispatch_message(make_message("after main", sender_open_id="ou_user", event_suffix="main_prompt"))

    session = runtime.backends["codex"].calls[-1][0]
    assert session.release_channel == "main"
    assert session.safety_mode == "read-only"
    assert any("已强制切到 main 稳定版本。" in message for message in messenger.messages)
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_sandbox_command_requires_admin_for_danger(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": FakeBackend()})

    await runtime.dispatch_message(make_message("/sandbox danger-full-access"))
    assert messenger.messages[-1] == "danger-full-access 只允许管理员切换。"

    await runtime.dispatch_message(make_message("/sandbox danger-full-access", sender_open_id="ou_admin", event_suffix="admin"))
    assert messenger.messages[-1] == "sandbox 已切换到 danger-full-access；当前 scope 会从下一条真实消息开始使用新 thread。"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_cwd_command_updates_scope_in_place(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    target_dir = config.main_workspace_dir / "docs"
    target_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": FakeBackend()})

    prompt = make_message("first task", event_suffix="cwd_before")
    session_key = runtime.session_scope.build_session_key(prompt)
    await runtime.dispatch_message(prompt)
    before = store.load_session(session_key)
    assert store.list_messages(before.session_id)

    await runtime.dispatch_message(make_message(f"/cwd {shlex.quote(str(target_dir))}", event_suffix="cwd_switch"))

    after = store.load_session(session_key)
    assert after.session_id == before.session_id
    assert after.cwd == str(target_dir)
    assert after.native_session_id == ""
    assert store.list_messages(after.session_id) == []
    assert messenger.messages[-1] == "\n".join(
        [
            "cwd 已切换到 docs。",
            "现在直接发消息，就会在这个目录进入 Codex。",
            "当前 scope 已原地更新；如需切回旧 thread，请用 /resume。",
        ]
    )
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_clear_command_keeps_scope_session_id(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": FakeBackend()})

    prompt = make_message("clear me", event_suffix="clear_before")
    session_key = runtime.session_scope.build_session_key(prompt)
    await runtime.dispatch_message(prompt)
    before = store.load_session(session_key)
    assert before.native_session_id == "native_1"
    assert store.list_messages(before.session_id)

    await runtime.dispatch_message(make_message("/clear", event_suffix="clear_now"))

    after = store.load_session(session_key)
    assert after.session_id == before.session_id
    assert after.native_session_id == ""
    assert store.list_messages(after.session_id) == []
    assert messenger.messages[-1] == "已清空当前上下文；当前 scope 保留原目录和配置。"
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

    runtime = RuntimeOrchestrator(
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
    assert sessions[0].start_calls == [
        {"receive_id": "oc_1", "reply_to_message_id": "om_stream", "root_id": ""}
    ]
    assert sessions[0].closed is True
    assert sessions[0].final_card is not None
    assert sessions[0].final_card["schema"] == "2.0"
    assert sessions[0].final_card["config"]["wide_screen_mode"] is True
    assert sessions[0].final_card["config"]["update_multi"] is True
    assert sessions[0].final_card["body"]["elements"][-1]["content"] == "echo: hello stream"
    assert typing.added == ["om_stream"]
    assert typing.removed
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_card_stream_mode_keeps_existing_thread_route_for_follow_up(tmp_path: Path) -> None:
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

    runtime = RuntimeOrchestrator(
        config,
        store,
        messenger,
        backends={"codex": FakeBackend()},
        streaming_session_factory=factory,
        typing_manager=typing,
    )

    await runtime.dispatch_message(
        IncomingMessage(
            event_id="evt_stream_follow_up",
            message_id="om_stream_follow_up",
            chat_id="oc_1",
            chat_type="p2p",
            sender_open_id="ou_user",
            root_id="om_root_existing",
            thread_id="omt_existing",
            text="continue thread",
            actionable=True,
        )
    )

    assert sessions
    assert sessions[0].start_calls == [
        {"receive_id": "oc_1", "reply_to_message_id": "om_stream_follow_up", "root_id": "om_root_existing"}
    ]
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_card_stream_mode_puts_reasoning_into_collapsible_panel(tmp_path: Path) -> None:
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

    runtime = RuntimeOrchestrator(
        config,
        store,
        messenger,
        backends={"codex": ReasoningBackend()},
        streaming_session_factory=factory,
        typing_manager=typing,
    )

    await runtime.dispatch_message(make_message("hello reasoning", event_suffix="reasoning"))

    assert sessions
    reasoning_panel = next(
        element
        for element in sessions[0].final_card["body"]["elements"]
        if isinstance(element, dict) and element.get("tag") == "collapsible_panel"
    )
    assert reasoning_panel["expanded"] is False
    assert "先检查 runtime。" in reasoning_panel["elements"][0]["content"]
    assert sessions[0].final_card["body"]["elements"][-1]["content"] == "done: hello reasoning"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_card_stream_mode_falls_back_to_text_after_final_card_failure(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.feishu.stream_mode = "card"
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    typing = FakeTypingManager()
    sessions: list[FailingFinalCardStreamingSession] = []

    def factory(current_messenger):
        session = FailingFinalCardStreamingSession(current_messenger)
        sessions.append(session)
        return session

    runtime = RuntimeOrchestrator(
        config,
        store,
        messenger,
        backends={"codex": FakeBackend()},
        streaming_session_factory=factory,
        typing_manager=typing,
    )

    await runtime.dispatch_message(make_message("hello fallback", event_suffix="stream_fallback"))

    assert sessions
    assert len(sessions[0].close_calls) == 2
    assert sessions[0].close_calls[0] is not None
    assert sessions[0].close_calls[1] is None
    assert sessions[0].closed is True
    assert messenger.messages[-1] == "echo: hello fallback"
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

    runtime = RuntimeOrchestrator(
        config,
        store,
        messenger,
        backends={"codex": SlowProgressBackend()},
        streaming_session_factory=factory,
        typing_manager=typing,
    )

    await asyncio.wait_for(runtime.dispatch_message(make_message("hello blocked stream", event_suffix="blocked_stream")), timeout=1)

    assert sessions
    assert sessions[0].started is True
    assert sessions[0].closed is True
    assert sessions[0].final_card is not None
    assert sessions[0].final_card["config"]["wide_screen_mode"] is True
    session = store.load_session(runtime.session_scope.build_session_key(make_message("hello blocked stream", event_suffix="blocked_stream")))
    assert session.native_session_id == "native_2"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_card_stream_rolls_over_to_new_card_in_same_thread_before_timeout(tmp_path: Path) -> None:
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
        session = ImmediateRolloverStreamingSession(current_messenger) if not sessions else FakeStreamingSession(current_messenger)
        session._message_id = f"om_stream_card_{len(sessions) + 1}"
        sessions.append(session)
        return session

    runtime = RuntimeOrchestrator(
        config,
        store,
        messenger,
        backends={"codex": SlowProgressBackend()},
        streaming_session_factory=factory,
        typing_manager=typing,
    )

    await runtime.dispatch_message(
        IncomingMessage(
            event_id="evt_stream_rollover",
            message_id="om_stream_rollover",
            chat_id="oc_1",
            chat_type="p2p",
            sender_open_id="ou_user",
            root_id="om_root_existing",
            thread_id="omt_existing",
            text="continue with rollover",
            actionable=True,
        )
    )

    assert len(sessions) == 2
    assert sessions[0].start_calls == [
        {"receive_id": "oc_1", "reply_to_message_id": "om_stream_rollover", "root_id": "om_root_existing"}
    ]
    assert sessions[0].needs_rollover() is True
    assert sessions[0].updates[-1]["freeze_notice"] == "此卡已停止流式更新，请继续查看当前 thread 中的新卡。"
    assert sessions[1].start_calls == [
        {"receive_id": "oc_1", "reply_to_message_id": "om_stream_rollover", "root_id": "om_root_existing"}
    ]
    assert sessions[1].closed is True
    assert sessions[1].final_card is not None
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
    backend.list_threads = NativeCommandBackend().list_threads  # type: ignore[attr-defined]
    backend.read_thread = NativeCommandBackend().read_thread  # type: ignore[attr-defined]
    backend.compact_thread = NativeCommandBackend().compact_thread  # type: ignore[attr-defined]
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

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
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    run_task = asyncio.create_task(runtime.dispatch_message(make_message("first", event_suffix="first")))
    await asyncio.wait_for(backend.first_started.wait(), timeout=1)

    await runtime.dispatch_message(
        IncomingMessage(
            event_id="evt_follow_1",
            message_id="om_follow_1",
            chat_id="oc_1",
            chat_type="p2p",
            sender_open_id="ou_user",
            root_id="om_first",
            thread_id="thread_first",
            text="补充一",
            actionable=True,
        )
    )
    await runtime.dispatch_message(
        IncomingMessage(
            event_id="evt_follow_2",
            message_id="om_follow_2",
            chat_id="oc_1",
            chat_type="p2p",
            sender_open_id="ou_user",
            root_id="om_first",
            thread_id="thread_first",
            text="补充二",
            actionable=True,
        )
    )

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
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    run_task = asyncio.create_task(runtime.dispatch_message(make_message("long running", event_suffix="queued_run")))
    await asyncio.wait_for(backend.first_started.wait(), timeout=1)

    await runtime.dispatch_message(
        IncomingMessage(
            event_id="evt_queued_follow_up",
            message_id="om_queued_follow_up",
            chat_id="oc_1",
            chat_type="p2p",
            sender_open_id="ou_user",
            root_id="om_queued_run",
            thread_id="thread_queued_run",
            text="补充 stop",
            actionable=True,
        )
    )
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
async def test_runtime_routes_card_action_approval_to_active_interaction(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = ApprovalRequestBackend()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    run_task = asyncio.create_task(runtime.dispatch_message(make_message("needs approval", event_suffix="needs_approval")))
    await asyncio.wait_for(backend.started.wait(), timeout=1)

    while not messenger.cards:
        await asyncio.sleep(0)
    prompt_card = messenger.cards[-1]
    prompt_commands = extract_card_commands(prompt_card)
    allow_once_command = next(command for command in prompt_commands if command.startswith("/__openrelay_interaction__") and command.endswith(" accept"))

    parsed = parse_card_action_event(
        {
            "token": "tok_interaction_accept",
            "operator": {"open_id": "ou_user"},
            "action": {"value": find_card_action_value(prompt_card, allow_once_command)},
            "context": {"open_chat_id": "oc_1", "open_message_id": "om_interaction_card"},
        }
    )
    assert parsed.message is not None

    await runtime.dispatch_message(parsed.message)
    await asyncio.wait_for(run_task, timeout=1)

    assert backend.decision == "accept"
    assert messenger.card_calls[-1]["update_message_id"] == "om_interaction_card"
    assert messenger.messages[-1] == "decision: accept"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_routes_text_reply_to_active_user_input_interaction(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = ToolUserInputBackend()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    run_task = asyncio.create_task(runtime.dispatch_message(make_message("needs env", event_suffix="needs_env")))
    await asyncio.wait_for(backend.started.wait(), timeout=1)

    while not messenger.cards:
        await asyncio.sleep(0)
    assert "Which environment should I deploy to?" in extract_card_text(messenger.cards[-1])

    await runtime.dispatch_message(
        IncomingMessage(
            event_id="evt_env_answer",
            message_id="om_env_answer",
            chat_id="oc_1",
            chat_type="p2p",
            sender_open_id="ou_user",
            root_id="om_needs_env",
            thread_id="thread_needs_env",
            text="production",
            actionable=True,
        )
    )
    await asyncio.wait_for(run_task, timeout=1)

    assert backend.answers == {"answers": {"deploy_env": {"answers": ["production"]}}}
    assert messenger.messages[-1] == "env: production"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_ping_bypasses_active_run_queue(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = QueuedFollowUpBackend()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    run_task = asyncio.create_task(runtime.dispatch_message(make_message("long running", event_suffix="run_ping")))
    await asyncio.wait_for(backend.first_started.wait(), timeout=1)

    await asyncio.wait_for(runtime.dispatch_message(make_message("/ping", event_suffix="ping_during_run")), timeout=1)

    assert messenger.messages[-1] == "pong"

    backend.release_first.set()
    await asyncio.wait_for(run_task, timeout=1)
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_serializes_messages_sharing_same_local_session_across_threads(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = NativeSessionConcurrencyBackend()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    shared_session = store.load_session("p2p:chat-a")
    shared_session.native_session_id = "native_shared"
    store.save_session(shared_session)
    store.bind_scope("p2p:chat-a:thread:root-a", shared_session.session_id)
    store.bind_scope("p2p:chat-a:thread:root-b", shared_session.session_id)

    first_message = IncomingMessage(
        event_id="evt_native_shared_1",
        message_id="om_native_shared_1",
        chat_id="chat-a",
        chat_type="p2p",
        sender_open_id="ou_user",
        root_id="root-a",
        thread_id="thread-a",
        text="first shared",
        actionable=True,
    )
    second_message = IncomingMessage(
        event_id="evt_native_shared_2",
        message_id="om_native_shared_2",
        chat_id="chat-a",
        chat_type="p2p",
        sender_open_id="ou_user",
        root_id="root-b",
        thread_id="thread-b",
        text="second shared",
        actionable=True,
    )
    first_started, first_released = backend._ensure_prompt("first shared")
    second_started, second_released = backend._ensure_prompt("second shared")

    first_task = asyncio.create_task(runtime.dispatch_message(first_message))
    await asyncio.wait_for(first_started.wait(), timeout=1)

    second_task = asyncio.create_task(runtime.dispatch_message(second_message))
    await asyncio.sleep(0.05)

    assert backend.start_order == ["first shared"]

    first_released.set()
    await asyncio.wait_for(second_started.wait(), timeout=1)
    second_released.set()
    await asyncio.wait_for(first_task, timeout=1)
    await asyncio.wait_for(second_task, timeout=1)

    assert backend.start_order == ["first shared", "second shared"]
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_allows_parallel_messages_for_different_local_sessions(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = NativeSessionConcurrencyBackend()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    first_session = store.load_session("p2p:chat-a")
    first_session.native_session_id = "native_a"
    store.save_session(first_session)
    second_session = store.create_next_session("p2p:chat-b", None, "parallel")
    second_session.native_session_id = "native_b"
    store.save_session(second_session)
    store.bind_scope("p2p:chat-a:thread:root-a", first_session.session_id)
    store.bind_scope("p2p:chat-b:thread:root-b", second_session.session_id)

    first_message = IncomingMessage(
        event_id="evt_native_parallel_1",
        message_id="om_native_parallel_1",
        chat_id="chat-a",
        chat_type="p2p",
        sender_open_id="ou_user",
        root_id="root-a",
        thread_id="thread-a",
        text="first parallel",
        actionable=True,
    )
    second_message = IncomingMessage(
        event_id="evt_native_parallel_2",
        message_id="om_native_parallel_2",
        chat_id="chat-b",
        chat_type="p2p",
        sender_open_id="ou_user",
        root_id="root-b",
        thread_id="thread-b",
        text="second parallel",
        actionable=True,
    )
    first_started, first_released = backend._ensure_prompt("first parallel")
    second_started, second_released = backend._ensure_prompt("second parallel")

    first_task = asyncio.create_task(runtime.dispatch_message(first_message))
    second_task = asyncio.create_task(runtime.dispatch_message(second_message))

    await asyncio.wait_for(first_started.wait(), timeout=1)
    await asyncio.wait_for(second_started.wait(), timeout=1)

    assert backend.start_order == ["first parallel", "second parallel"]

    first_released.set()
    second_released.set()
    await asyncio.wait_for(first_task, timeout=1)
    await asyncio.wait_for(second_task, timeout=1)
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_uses_local_images_as_backend_input(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = ImageAwareBackend()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake-image")
    message = IncomingMessage(
        event_id="evt_image_runtime",
        message_id="om_image_runtime",
        chat_id="oc_image",
        chat_type="p2p",
        sender_open_id="ou_user",
        text="[图片]",
        local_image_paths=(str(image_path),),
        actionable=True,
    )

    await runtime.dispatch_message(message)

    assert backend.prompts == [DEFAULT_IMAGE_PROMPT]
    assert backend.image_paths == [(str(image_path),)]
    session = store.load_session(runtime.session_scope.build_session_key(message))
    assert store.list_messages(session.session_id)[0]["content"] == "[图片]"
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
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": FakeBackend()})

    await runtime.dispatch_message(make_message("/cwd subdir", event_suffix="cwd"))

    assert messenger.text_calls[-1]["force_new_message"] is False
    assert messenger.text_calls[-1]["reply_to_message_id"] == "om_cwd"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_thread_reply_reuses_top_level_thread_scope(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = FakeBackend()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    top_level = make_message("first task", event_suffix="root")
    await runtime.dispatch_message(top_level)
    control_message = make_message("/help", event_suffix="root_help")

    thread_reply = IncomingMessage(
        event_id="evt_thread_follow_up",
        message_id="om_thread_follow_up",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id="ou_user",
        root_id="om_root",
        thread_id="thread_1",
        text="follow up in thread",
        actionable=True,
    )

    assert runtime.session_scope.build_session_key(top_level) == "p2p:oc_1:thread:om_root"
    assert runtime.session_scope.build_session_key(control_message) == "p2p:oc_1"
    assert runtime.session_scope.build_session_key(thread_reply) == runtime.session_scope.build_session_key(top_level)

    await runtime.dispatch_message(thread_reply)

    assert len(backend.calls) == 2
    assert backend.calls[1][0].native_session_id == "native_1"
    session = store.load_session(runtime.session_scope.build_session_key(top_level))
    assert [entry["content"] for entry in store.list_messages(session.session_id)] == [
        "first task",
        "echo: first task",
        "follow up in thread",
        "echo: follow up in thread",
    ]
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_thread_id_only_follow_up_reuses_original_thread_session_after_owner_switch(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = ThreadAwareFakeMessenger()
    backend = FakeBackend()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    await runtime.dispatch_message(make_message("first task", event_suffix="root"))
    first_session = store.load_session("p2p:oc_1:thread:om_root")

    await runtime.dispatch_message(make_message("second task", event_suffix="other"))
    second_session = store.load_session("p2p:oc_1:thread:om_other")

    thread_reply = IncomingMessage(
        event_id="evt_thread_only_follow_up",
        message_id="om_thread_only_follow_up",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id="ou_user",
        thread_id="thread_fixed",
        text="continue first thread",
        actionable=True,
    )

    await runtime.dispatch_message(thread_reply)

    assert first_session.session_id != second_session.session_id
    assert backend.calls[-1][0].session_id == first_session.session_id
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_resume_binds_top_level_thread_scope_to_existing_session(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = FakeBackend()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    existing = store.load_session("p2p:oc_1")
    existing.native_session_id = "native_existing"
    store.save_session(existing)

    await runtime.dispatch_message(make_message(f"/resume {existing.session_id}", event_suffix="resume_existing"))

    thread_reply = IncomingMessage(
        event_id="evt_resume_follow_up",
        message_id="om_resume_follow_up",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id="ou_user",
        root_id="om_resume_existing",
        thread_id="thread_resume_existing",
        text="continue existing",
        actionable=True,
    )

    await runtime.dispatch_message(thread_reply)

    assert backend.calls[-1][0].session_id == existing.session_id
    assert backend.calls[-1][0].native_session_id == "native_existing"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_resume_card_action_connects_thread_to_native_session(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = NativeCommandBackend()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    await runtime.dispatch_message(make_message("/resume", event_suffix="resume_card"))
    resume_card = messenger.cards[-1]

    connect_action = parse_card_action_event(
        {
            "token": "tok_resume_connect",
            "operator": {"open_id": "ou_user"},
            "action": {"value": find_card_action_value(resume_card, "/resume native_old")},
            "context": {"open_chat_id": "oc_1", "open_message_id": "om_resume_card"},
        }
    )
    assert connect_action.message is not None

    await runtime.dispatch_message(connect_action.message)

    assert messenger.messages[-1].startswith("已连接 Codex 会话：name native_old")
    assert messenger.text_calls[-1]["reply_to_message_id"] == "om_resume_card"
    assert messenger.text_calls[-1]["force_new_message"] is False

    thread_reply = IncomingMessage(
        event_id="evt_resume_card_follow_up",
        message_id="om_resume_card_follow_up",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id="ou_user",
        root_id="om_resume_card",
        thread_id="thread_resume_card",
        text="continue connected thread",
        actionable=True,
    )

    await runtime.dispatch_message(thread_reply)

    assert backend.calls[-1][0].native_session_id == "native_old"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_reply_chain_without_thread_ids_reuses_previous_bot_reply_alias(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = FakeBackend()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    await runtime.dispatch_message(make_message("first task", event_suffix="first"))

    follow_up = IncomingMessage(
        event_id="evt_parent_follow_up",
        message_id="om_parent_follow_up",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id="ou_user",
        parent_id="om_bot_1",
        text="continue from reply",
        actionable=True,
    )

    assert runtime.session_scope.build_session_key(follow_up) == "p2p:oc_1:thread:om_first"

    await runtime.dispatch_message(follow_up)

    assert len(backend.calls) == 2
    assert backend.calls[1][0].native_session_id == "native_1"
    session = store.load_session("p2p:oc_1:thread:om_first")
    assert [entry["content"] for entry in store.list_messages(session.session_id)] == [
        "first task",
        "echo: first task",
        "continue from reply",
        "echo: continue from reply",
    ]
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_reply_chain_reuses_alias_when_user_replies_to_previous_user_message(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = FakeBackend()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    await runtime.dispatch_message(make_message("first task", event_suffix="first"))

    first_follow_up = IncomingMessage(
        event_id="evt_parent_follow_up_1",
        message_id="om_parent_follow_up_1",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id="ou_user",
        parent_id="om_bot_1",
        text="continue from reply",
        actionable=True,
    )
    await runtime.dispatch_message(first_follow_up)

    second_follow_up = IncomingMessage(
        event_id="evt_parent_follow_up_2",
        message_id="om_parent_follow_up_2",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id="ou_user",
        parent_id="om_parent_follow_up_1",
        text="continue again",
        actionable=True,
    )

    assert runtime.session_scope.build_session_key(second_follow_up) == "p2p:oc_1:thread:om_first"

    await runtime.dispatch_message(second_follow_up)

    assert len(backend.calls) == 3
    assert backend.calls[-1][0].native_session_id == "native_1"
    session = store.load_session("p2p:oc_1:thread:om_first")
    assert [entry["content"] for entry in store.list_messages(session.session_id)] == [
        "first task",
        "echo: first task",
        "continue from reply",
        "echo: continue from reply",
        "continue again",
        "echo: continue again",
    ]
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_thread_follow_up_uses_root_id_scope_directly(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = FakeBackend()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    top_level = make_message("first task", event_suffix="root_direct")
    await runtime.dispatch_message(top_level)

    thread_follow_up = IncomingMessage(
        event_id="evt_thread_root_direct_follow_up",
        message_id="om_thread_root_direct_follow_up",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id="ou_user",
        root_id="om_root_direct",
        thread_id="omt_root_direct",
        parent_id="om_some_other_parent",
        text="follow up in thread",
        actionable=True,
    )

    assert runtime.session_scope.build_session_key(thread_follow_up) == "p2p:oc_1:thread:om_root_direct"
    await runtime.dispatch_message(thread_follow_up)

    assert len(backend.calls) == 2
    assert backend.calls[-1][0].session_id == store.load_session("p2p:oc_1:thread:om_root_direct").session_id
    assert backend.calls[-1][0].native_session_id == "native_1"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_persists_native_thread_id_before_backend_returns(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = ThreadAwareNativeBackend()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    message = make_message("start native thread", event_suffix="native_early")
    await runtime.dispatch_message(message)

    session = store.load_session(runtime.session_scope.build_session_key(message))
    assert backend.thread_ids_seen_in_callback == ["native_started_1"]
    assert session.native_session_id == "native_started_1"
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_group_thread_reply_reuses_top_level_thread_scope(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = FakeBackend()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    top_level = IncomingMessage(
        event_id="evt_group_root",
        message_id="om_group_root",
        chat_id="oc_group_1",
        chat_type="group",
        sender_open_id="ou_user",
        text="group first task",
        actionable=True,
    )
    await runtime.dispatch_message(top_level)

    thread_reply = IncomingMessage(
        event_id="evt_group_thread",
        message_id="om_group_thread",
        chat_id="oc_group_1",
        chat_type="group",
        sender_open_id="ou_user",
        root_id="om_group_root",
        thread_id="thread_group_1",
        text="group follow up",
        actionable=True,
    )

    assert runtime.session_scope.build_session_key(top_level) == "group:oc_group_1:thread:om_group_root:sender:ou_user"
    assert runtime.session_scope.build_session_key(thread_reply) == runtime.session_scope.build_session_key(top_level)

    await runtime.dispatch_message(thread_reply)

    session = store.load_session(runtime.session_scope.build_session_key(top_level))
    assert [entry["content"] for entry in store.list_messages(session.session_id)] == [
        "group first task",
        "echo: group first task",
        "group follow up",
        "echo: group follow up",
    ]
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_top_level_resume_list_is_not_blocked_by_active_thread_run(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    backend = InterruptibleBackend()
    native_helper = NativeCommandBackend()
    backend.list_threads = native_helper.list_threads  # type: ignore[attr-defined]
    backend.read_thread = native_helper.read_thread  # type: ignore[attr-defined]
    backend.compact_thread = native_helper.compact_thread  # type: ignore[attr-defined]
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": backend})

    run_task = asyncio.create_task(runtime.dispatch_message(make_message("long running", event_suffix="resume_lock_run")))
    await asyncio.wait_for(backend.started.wait(), timeout=1)

    await runtime.dispatch_message(make_message("/resume", event_suffix="resume_lock_list"))

    assert messenger.cards
    assert "Codex 会话" in extract_card_text(messenger.cards[-1])
    assert all("已收到补充" not in message for message in messenger.messages)

    await runtime.dispatch_message(make_message("/stop", event_suffix="resume_lock_stop"))
    await asyncio.wait_for(run_task, timeout=1)
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
    workspace = SessionWorkspaceService(config)

    resolved = workspace.resolve_cwd(session.cwd, "~/main/repo", session)

    assert resolved == target.resolve()
    store.close()


def test_session_ux_resolve_cwd_rejects_missing_path(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    session = store.load_session("p2p:oc_1")
    workspace = SessionWorkspaceService(config)

    with pytest.raises(ValueError, match=r"path does not exist: missing-dir"):
        workspace.resolve_cwd(session.cwd, "missing-dir", session)
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
    workspace = SessionWorkspaceService(config)

    with pytest.raises(ValueError, match=r"not a directory: README\.md"):
        workspace.resolve_cwd(session.cwd, "README.md", session)
    store.close()


@pytest.mark.asyncio
async def test_runtime_cwd_command_rejects_missing_path(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.workspace_root.mkdir(parents=True, exist_ok=True)
    config.main_workspace_dir.mkdir(parents=True, exist_ok=True)
    config.develop_workspace_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": FakeBackend()})

    await runtime.dispatch_message(make_message("/cwd missing-dir", event_suffix="cwd_missing"))

    session = store.load_session(runtime.session_scope.build_session_key(make_message("x")))
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
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": FakeBackend()})

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
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": FakeBackend()})

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
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": FakeBackend()})

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

    monkeypatch.setattr("openrelay.runtime.restart.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("openrelay.runtime.restart.is_systemd_service_process", lambda env=None, pid=None: True)
    monkeypatch.setattr(runtime.restart_controller, "_restart_systemd_service", fake_restart_systemd_service)
    monkeypatch.setattr("openrelay.runtime.restart.CodexBackend.shutdown_all", fake_shutdown_all)
    monkeypatch.setattr("openrelay.runtime.restart.os.execvpe", fake_execvpe)

    await runtime.restart_controller._restart_process()

    assert systemd_calls == ["openrelay.service"]
    assert shutdown_calls == []
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_restart_process_execs_and_shuts_down_backends(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = make_config(tmp_path)
    store = StateStore(config)
    messenger = FakeMessenger()
    runtime = RuntimeOrchestrator(config, store, messenger, backends={"codex": FakeBackend()})

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

    monkeypatch.setattr("openrelay.runtime.restart.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("openrelay.runtime.restart.is_systemd_service_process", lambda env=None, pid=None: False)
    monkeypatch.setattr(runtime.restart_controller, "_restart_systemd_service", fake_restart_systemd_service)
    monkeypatch.setattr("openrelay.runtime.restart.os.execvpe", fake_execvpe)
    monkeypatch.setattr("openrelay.runtime.restart.CodexBackend.shutdown_all", fake_shutdown_all)

    await runtime.restart_controller._restart_process()

    assert shutdown_calls == ["shutdown"]
    assert exec_calls
    assert exec_calls[0][0]
    assert exec_calls[0][1][-2:] == ["-m", "openrelay"]
    await runtime.shutdown()
