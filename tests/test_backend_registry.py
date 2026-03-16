from pathlib import Path

from openrelay.backends.registry import build_builtin_backend_descriptors, instantiate_builtin_backends
from openrelay.core import AppConfig, BackendConfig, FeishuConfig


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
        backend=BackendConfig(default_backend="codex", codex_sessions_dir=tmp_path / "native"),
    )


def test_builtin_backend_descriptors_keep_codex_metadata_without_instantiating_legacy_backend(tmp_path: Path) -> None:
    descriptors = build_builtin_backend_descriptors()

    assert descriptors["codex"].transport == "cli-app-server"
    assert descriptors["codex"].factory is None
    assert instantiate_builtin_backends(make_config(tmp_path), descriptors) == {}
