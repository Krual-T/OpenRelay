from pathlib import Path

from openrelay.core import AppConfig, BackendConfig, FeishuConfig
from openrelay.presentation.session import SessionPresentation
from openrelay.runtime import HelpRenderer
from openrelay.session import SessionShortcutService, SessionWorkspaceService
from openrelay.storage import StateStore



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
        backend=BackendConfig(codex_sessions_dir=tmp_path / "native"),
    )



def prepare_dirs(config: AppConfig) -> None:
    for path in [config.workspace_root, config.main_workspace_dir, config.develop_workspace_dir, config.backend.codex_sessions_dir]:
        path.mkdir(parents=True, exist_ok=True)



def test_help_renderer_describes_empty_session(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    prepare_dirs(config)
    store = StateStore(config)
    session = store.load_session("p2p:oc_1")
    session_ux = SessionPresentation(config, store)
    workspace = SessionWorkspaceService(config)
    shortcuts = SessionShortcutService(config, store, workspace)
    renderer = HelpRenderer(config, store, session_ux, workspace, shortcuts)

    text = renderer.build_text(session, ["codex"])

    assert "OpenRelay 帮助" in text
    assert "- 会话阶段：未开始（还没发第一条真实需求）" in text
    assert "- 后端线程：pending（直接发消息就会创建）" in text
    assert "- 最近关注：还没有可总结的本地上下文" in text
    assert "- `/workspace`：打开工作区浏览器。" in text
    assert "- `/panel`：已移除；会话用 `/resume`，工作区用 `/workspace`，状态用 `/status`。" in text
    store.close()



def test_help_renderer_describes_active_session(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    prepare_dirs(config)
    store = StateStore(config)
    session = store.load_session("p2p:oc_1")
    store.append_message(session.session_id, "user", "hello help")
    store.append_message(session.session_id, "assistant", "echo: hello help")
    session.native_session_id = "native_1"
    session.last_usage = {"input_tokens": 100, "cached_input_tokens": 50, "output_tokens": 20, "total_tokens": 170, "model_context_window": 1000}
    store.save_session(session)
    session = store.get_session(session.session_id)
    session_ux = SessionPresentation(config, store)
    workspace = SessionWorkspaceService(config)
    shortcuts = SessionShortcutService(config, store, workspace)
    renderer = HelpRenderer(config, store, session_ux, workspace, shortcuts)

    text = renderer.build_text(session, ["codex", "claude"])

    assert "- 会话阶段：进行中（继续发消息会沿用当前后端线程）" in text
    assert "- 上下文占用：17.0% (170/1000)" in text
    assert "- 最近关注：用户：hello help | 助手：echo: hello help" in text
    assert "- 切后端：/backend [list|codex|claude]。" in text
    assert "- `/backend <codex|claude>`：切换 backend；从下一条真实消息开始生效。" in text
    store.close()
