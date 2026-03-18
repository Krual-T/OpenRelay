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



def test_help_renderer_lists_commands_for_single_backend(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    prepare_dirs(config)
    store = StateStore(config)
    session = store.load_session("p2p:oc_1")
    session_ux = SessionPresentation(config, store)
    workspace = SessionWorkspaceService(config)
    shortcuts = SessionShortcutService(config, store, workspace)
    renderer = HelpRenderer(config, store, session_ux, workspace, shortcuts)

    text = renderer.build_text(session, ["codex"])

    assert text.startswith("OpenRelay 帮助")
    assert "会话与信息：" in text
    assert "- `/resume`：打开可恢复会话列表。" in text
    assert "- `/workspace`：打开工作区浏览器。" in text
    assert "- `/model <name|default>`：切换模型。" in text
    assert "- `/panel`：已移除；改用 `/resume`、`/workspace`、`/status`。" in text
    assert "当前状态：" not in text
    assert "你现在最该做什么：" not in text
    assert "下一条消息可以直接这样发：" not in text
    store.close()



def test_help_renderer_lists_backend_switch_when_multiple_backends(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    prepare_dirs(config)
    store = StateStore(config)
    session = store.load_session("p2p:oc_1")
    session_ux = SessionPresentation(config, store)
    workspace = SessionWorkspaceService(config)
    shortcuts = SessionShortcutService(config, store, workspace)
    renderer = HelpRenderer(config, store, session_ux, workspace, shortcuts)

    text = renderer.build_text(session, ["codex", "claude"])

    assert "- `/backend list`：查看可用 backend。" in text
    assert "- `/backend <codex|claude>`：切换 backend。" in text
    store.close()
