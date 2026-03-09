from pathlib import Path

from openrelay.config import load_config



def test_env_file_overrides_empty_exported_values(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FEISHU_APP_ID", "")
    monkeypatch.setenv("FEISHU_APP_SECRET", "")
    monkeypatch.setenv("FEISHU_VERIFY_TOKEN", "")
    monkeypatch.setenv("WORKSPACE_DIR", "")
    (tmp_path / ".env").write_text(
        """
FEISHU_APP_ID=cli_test
FEISHU_APP_SECRET=secret_test
FEISHU_VERIFY_TOKEN=verify_test
WORKSPACE_DIR=.
""".strip() + "\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.feishu.app_id == "cli_test"
    assert config.feishu.app_secret == "secret_test"
    assert config.feishu.verify_token == "verify_test"
    assert config.workspace_root == tmp_path.resolve()



def test_load_config_accepts_supported_env_names(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FEISHU_APP_ID", "cli_test")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret_test")
    monkeypatch.setenv("WORKSPACE_DIR", "workspace")
    monkeypatch.setenv("MAIN_WORKSPACE_DIR", "main")
    monkeypatch.setenv("DEVELOP_WORKSPACE_DIR", "develop")
    monkeypatch.setenv("MODEL_BACKEND", "codex-cli")
    monkeypatch.setenv("MODEL_NAME", "gpt-5.4")
    monkeypatch.setenv("CODEX_CLI_PATH", "codex")
    monkeypatch.setenv("CODEX_SANDBOX", "read-only")
    config = load_config(tmp_path)
    assert config.backend.default_backend == "codex"
    assert config.backend.default_model == "gpt-5.4"
    assert config.backend.default_safety_mode == "read-only"
    assert config.backend.codex_cli_path == "codex"
    assert config.workspace_root == (tmp_path / "workspace").resolve()
    assert config.main_workspace_dir == (tmp_path / "main").resolve()
    assert config.develop_workspace_dir == (tmp_path / "develop").resolve()



def test_verify_token_is_optional(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FEISHU_APP_ID", "cli_test")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret_test")
    monkeypatch.delenv("FEISHU_VERIFY_TOKEN", raising=False)
    config = load_config(tmp_path)
    assert config.feishu.verify_token == ""
