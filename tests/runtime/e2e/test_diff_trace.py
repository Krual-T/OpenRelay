from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from openrelay.agent_runtime.service import AgentRuntimeService
from openrelay.backends.codex_adapter.backend import CodexRuntimeBackend
from openrelay.core import BackendReply, IncomingMessage, SessionRecord
from openrelay.presentation.live_turn import LiveTurnPresenter
from openrelay.runtime.turn import TurnRuntimeContext
from openrelay.runtime.turn_application import TurnApplicationService
from openrelay.runtime.turn_run_controller import TurnRunController
from openrelay.runtime.turn_runtime_event_bridge import TurnRuntimeEventBridge
from tests.support.e2e_runtime import (
    FakeStore,
    FakeStreamingSession,
    FakeTypingManager,
    InMemoryBindingStore,
    build_e2e_session,
    extract_markdown_blocks,
)


class FakeDiffClient:
    def __init__(
        self,
        codex_path: str,
        workspace_root: Path,
        sqlite_home: Path,
        model: str,
        safety_mode: str,
        **_: object,
    ) -> None:
        self.codex_path = codex_path
        self.workspace_root = workspace_root
        self.sqlite_home = sqlite_home
        self.model = model
        self.safety_mode = safety_mode
        self.active_turns: set[object] = set()
        self.started = 0
        self.turn_start_params: list[dict[str, object]] = []

    async def request(self, method: str, params: dict[str, object], **_: object) -> dict[str, object]:
        if method == "thread/start":
            self.started += 1
            return {
                "thread": {
                    "id": f"thread_{self.started}",
                    "preview": "preview",
                    "updatedAt": "2026-03-18T00:00:00Z",
                    "status": "idle",
                }
            }
        if method == "thread/resume":
            return {"thread": {"id": str(params.get("threadId") or "")}}
        if method == "turn/start":
            self.turn_start_params.append(params)
            turn = next(iter(self.active_turns))
            await turn.handle_notification(
                self,
                "turn/started",
                {"threadId": "thread_1", "turn": {"id": "turn_1"}},
            )
            await turn.handle_notification(
                self,
                "item/completed",
                {
                    "threadId": "thread_1",
                    "turnId": "turn_1",
                    "item": {
                        "id": "fc_1",
                        "type": "fileChange",
                        "changes": [
                            {
                                "path": "/home/Shaokun.Tang/Projects/tool-demo-edit.txt",
                                "kind": {"type": "update"},
                            },
                            {
                                "path": "/home/Shaokun.Tang/Projects/tool-demo-new.txt",
                                "kind": {"type": "add"},
                            },
                        ],
                    },
                },
            )
            await turn.handle_notification(
                self,
                "turn/diff/updated",
                {
                    "threadId": "thread_1",
                    "turnId": "turn_1",
                    "diff": (
                        "--- a/tool-demo-edit.txt\n"
                        "+++ b/tool-demo-edit.txt\n"
                        "@@ -1,2 +1,3 @@\n"
                        "-状态: 旧值\n"
                        "+状态: 第三次更新完成\n"
                        "+补充: 这一行是本次新增，用来观察插入行在 diff 里的显示。"
                    ),
                },
            )
            await turn.handle_notification(
                self,
                "item/agentMessage/delta",
                {
                    "threadId": "thread_1",
                    "turnId": "turn_1",
                    "itemId": "msg_1",
                    "delta": "已演示 edit 和 update 文件工具。",
                },
            )
            await turn.handle_notification(
                self,
                "item/completed",
                {
                    "threadId": "thread_1",
                    "turnId": "turn_1",
                    "item": {
                        "id": "msg_1",
                        "type": "agentMessage",
                        "text": "已演示 edit 和 update 文件工具。",
                    },
                },
            )
            await turn.handle_notification(
                self,
                "turn/completed",
                {"threadId": "thread_1", "turnId": "turn_1", "turn": {"status": "completed"}},
            )
            return {"turn": {"id": "turn_1"}}
        if method == "turn/interrupt":
            return {}
        raise AssertionError(f"unexpected request: {method}")

    async def list_threads(self, limit: int = 20) -> tuple[list[object], str]:
        _ = limit
        return ([], "")

    async def read_thread(self, thread_id: str, *, include_turns: bool = True) -> object:
        _ = thread_id, include_turns
        return object()

    async def _send_server_result(self, request_id: int | str, result: dict[str, object]) -> None:
        _ = request_id, result

    async def shutdown(self) -> None:
        return


def _build_message() -> IncomingMessage:
    return IncomingMessage(
        event_id="evt_diff",
        message_id="om_input",
        chat_id="oc_test",
        chat_type="p2p",
        sender_open_id="ou_user",
        text="正在飞书debug看看diff效果 演示一下edit和update文件工具",
        actionable=True,
    )


@pytest.mark.asyncio
async def test_e2e_diff_trace_reaches_feishu_final_card(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("openrelay.backends.codex_adapter.transport.CodexAppServerClient", FakeDiffClient)

    backend = CodexRuntimeBackend(
        codex_path="codex",
        default_model="gpt-test",
        workspace_root=tmp_path,
        sqlite_home=tmp_path / "sqlite",
    )
    binding_store = InMemoryBindingStore()
    runtime_service = AgentRuntimeService({"codex": backend}, binding_store)  # type: ignore[arg-type]

    session = build_e2e_session(tmp_path)
    store = FakeStore(session)
    streaming = FakeStreamingSession()
    final_replies: list[BackendReply] = []

    presenter = LiveTurnPresenter()

    async def reply_final(
        message: IncomingMessage,
        text: str,
        active_streaming: FakeStreamingSession | None,
        live_state: dict[str, Any] | None,
        trace_context: object | None = None,
    ) -> None:
        _ = message, trace_context
        final_replies.append(BackendReply(text=text))
        if active_streaming is not None and active_streaming.has_started():
            await active_streaming.close(presenter.build_final_card(live_state or {}, fallback_text=text))

    runtime = TurnRuntimeContext(
        config=SimpleNamespace(feishu=SimpleNamespace(stream_mode="card")),
        store=store,
        messenger=object(),
        typing_manager=FakeTypingManager(),
        session_ux=SimpleNamespace(
            format_cwd=lambda cwd, session=None, release_channel=None: str(cwd),
            label_session_if_needed=lambda current, summary: current,
            shorten=lambda text, max_length=96: str(text)[:max_length],
        ),
        streaming_session_factory=lambda current_messenger: streaming,
        execution_coordinator=SimpleNamespace(start_run=lambda *args, **kwargs: None, finish_run=lambda *args, **kwargs: None),
        build_card_action_context=lambda message, session_key: {},
        streaming_route_for_message=lambda message: SimpleNamespace(reply_to_message_id="", root_id="", force_new_message=False),
        root_id_for_message=lambda message: "",
        is_card_action_message=lambda message: False,
        build_session_key=lambda message: "session:test",
        remember_outbound_aliases=lambda message, session_key, alias_ids: None,
        reply_final=reply_final,
        live_turn_presenter=presenter,
        binding_store=binding_store,  # type: ignore[arg-type]
        runtime_service=runtime_service,
    )
    controller = TurnRunController(runtime, _build_message(), "session:relay_1", presenter)
    controller.initialize(session)
    application = TurnApplicationService(
        runtime,
        _build_message(),
        "session:relay_1",
        controller,
        TurnRuntimeEventBridge(runtime, controller, presenter),
    )

    prompt = "正在飞书debug看看diff效果 演示一下edit和update文件工具"
    await application.run(prompt, prompt)

    assert streaming.final_card is not None
    assert final_replies[-1].text == "已演示 edit 和 update 文件工具。"

    markdown_blocks = extract_markdown_blocks(streaming.final_card)
    rendered_card_text = "\n\n".join(markdown_blocks)

    client = next(iter(backend._clients.values())).transport._client
    assert client is not None
    assert client.turn_start_params[0]["input"] == [{"type": "text", "text": prompt}]
    assert "🟠 **Updated files**" in rendered_card_text
    assert "<text_tag color='orange'>Edit</text_tag> `/home/Shaokun.Tang/Projects/tool-demo-edit.txt`" in rendered_card_text
    assert "<text_tag color='green'>Add</text_tag> `/home/Shaokun.Tang/Projects/tool-demo-new.txt`" in rendered_card_text
    assert "<font color='grey'>---&nbsp;a/tool-demo-edit.txt</font>" in rendered_card_text
    assert "<font color='grey'>+++&nbsp;b/tool-demo-edit.txt</font>" in rendered_card_text
    assert "<text_tag color='red'>-</text_tag>&nbsp;<font color='red'>状态:&nbsp;旧值</font>" in rendered_card_text
    assert "<text_tag color='green'>+</text_tag>&nbsp;<font color='green'>状态:&nbsp;第三次更新完成</font>" in rendered_card_text
    assert "已演示 edit 和 update 文件工具。" in rendered_card_text
