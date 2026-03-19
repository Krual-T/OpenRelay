import logging
from dataclasses import replace
from pathlib import Path

from openrelay.agent_runtime import SessionLocator, SessionSummary, SessionTranscript
from openrelay.agent_runtime.models import TranscriptMessage
from openrelay.core import AppConfig, IncomingMessage, SessionRecord, get_release_workspace
from openrelay.presentation.runtime_status import RuntimeStatusPresenter
from openrelay.presentation.session import SessionPresentation
from openrelay.release import ReleaseCommandService
from openrelay.runtime import HelpRenderer
from openrelay.runtime import RuntimeCommandHooks, RuntimeCommandRouter
from openrelay.session import (
    SessionBrowser,
    SessionScopeResolver,
    SessionShortcutService,
    SessionWorkspaceService,
)
from openrelay.storage import StateStore
from tests.support.app import make_app_config, make_incoming_message, prepare_app_dirs
from tests.support.runtime import FakeNativeMessage, FakeNativeThread, RuntimeBackendStub


class FakeRuntimeService:
    def __init__(self, cwd: str) -> None:
        self.cwd = cwd
        self.list_calls: list[int] = []
        self.read_calls: list[str] = []
        self.compact_calls: list[str] = []
        self.backends = {"codex": RuntimeBackendStub(supports_session_list=True, supports_compact=True)}
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


class FakeSessionMutationService:
    def __init__(self, config: AppConfig, store: StateStore, session_ux: SessionPresentation) -> None:
        self.config = config
        self.store = store
        self.session_ux = session_ux

    def clear_context(self, scope_key: str, current: SessionRecord) -> SessionRecord:
        return self._update_scope_session(
            scope_key,
            current,
            native_session_id="",
            last_usage={},
            clear_messages=True,
        )

    def switch_model(self, scope_key: str, current: SessionRecord, model_override: str) -> SessionRecord:
        return self._update_scope_session(
            scope_key,
            current,
            model_override=model_override,
            native_session_id="",
            last_usage={},
            clear_messages=True,
        )

    def switch_sandbox(self, scope_key: str, current: SessionRecord, safety_mode: str) -> SessionRecord:
        return self._update_scope_session(
            scope_key,
            current,
            safety_mode=safety_mode,
            native_session_id="",
            last_usage={},
            clear_messages=True,
        )

    def switch_backend(self, scope_key: str, current: SessionRecord, backend: str) -> SessionRecord:
        return self._update_scope_session(
            scope_key,
            current,
            backend=backend,
            native_session_id="",
            last_usage={},
            clear_messages=True,
        )

    def switch_cwd(self, scope_key: str, current: SessionRecord, cwd: Path) -> SessionRecord:
        return self._update_scope_session(
            scope_key,
            current,
            cwd=str(cwd),
            native_session_id="",
            last_usage={},
            clear_messages=True,
        )

    def switch_release_channel(self, scope_key: str, current: SessionRecord, channel: str, label: str) -> SessionRecord:
        updates: dict[str, object] = {
            "label": label,
            "release_channel": channel,
            "cwd": str(get_release_workspace(self.config, channel)),
            "native_session_id": "",
            "last_usage": {},
        }
        if channel == "main":
            updates["safety_mode"] = "read-only"
        return self._update_scope_session(scope_key, current, clear_messages=True, **updates)

    def reset_scope(self, scope_key: str) -> SessionRecord:
        self.store.clear_sessions(scope_key)
        return self.store.load_session(scope_key)

    def bind_native_thread(
        self,
        scope_key: str,
        current: SessionRecord,
        thread_id: str,
        *,
        cwd: str | None = None,
        label: str = "",
    ) -> SessionRecord:
        updates: dict[str, object] = {
            "native_session_id": thread_id.strip(),
            "release_channel": "",
            "last_usage": {},
        }
        if cwd:
            updates["cwd"] = cwd
        if label:
            updates["label"] = label
        return self._update_scope_session(scope_key, current, clear_messages=True, **updates)

    def save_directory_shortcut(self, shortcut) -> object:
        return self.store.save_directory_shortcut(shortcut)

    def remove_directory_shortcut(self, name: str) -> bool:
        return self.store.remove_directory_shortcut(name)

    def _update_scope_session(
        self,
        scope_key: str,
        current: SessionRecord,
        *,
        clear_messages: bool = False,
        **updates: object,
    ) -> SessionRecord:
        next_session = replace(current, **updates)
        saved = self.store.save_scope_session(scope_key, next_session)
        if clear_messages:
            self.store.clear_session_messages(saved.session_id)
        return self.store.get_session(saved.session_id)


def make_config(tmp_path: Path) -> AppConfig:
    projects_dir = tmp_path / "home" / "Projects"
    return make_app_config(
        tmp_path,
        workspace_root=tmp_path / "home",
        main_workspace_dir=projects_dir,
        develop_workspace_dir=tmp_path / "home" / "develop",
        workspace_default_dir=projects_dir,
    )


def prepare_dirs(config: AppConfig) -> None:
    prepare_app_dirs(config, include_data_dir=False)


def make_message(text: str, sender_open_id: str = "ou_user", suffix: str = "cmd") -> IncomingMessage:
    return make_incoming_message(text, event_suffix=suffix, sender_open_id=sender_open_id)


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
    session_mutations = FakeSessionMutationService(config, store, session_ux)
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
