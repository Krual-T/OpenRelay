import json

import pytest

from openrelay.config import ConfigError, load_config


REQUIRED_ENV = {
    "FEISHU_APP_ID": "app",
    "FEISHU_APP_SECRET": "secret",
}


def apply_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)


def test_load_config_parses_directory_shortcuts(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    apply_required_env(monkeypatch)
    monkeypatch.setenv(
        "DIRECTORY_SHORTCUTS",
        json.dumps(
            [
                {"name": "docs", "path": "docs", "channels": "main"},
                {"name": "api", "path": "services/api", "channels": "develop"},
                {"name": "shared", "path": "shared", "channels": "all"},
            ]
        ),
    )

    config = load_config(tmp_path)

    assert [shortcut.name for shortcut in config.directory_shortcuts] == ["docs", "api", "shared"]
    assert config.directory_shortcuts[0].channels == ("main",)
    assert config.directory_shortcuts[2].channels == ("all",)


def test_load_config_rejects_overlapping_directory_shortcut_names(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    apply_required_env(monkeypatch)
    monkeypatch.setenv(
        "DIRECTORY_SHORTCUTS",
        json.dumps(
            [
                {"name": "repo", "path": "repo-a", "channels": "all"},
                {"name": "repo", "path": "repo-b", "channels": "develop"},
            ]
        ),
    )

    with pytest.raises(ConfigError, match="Duplicate directory shortcut name"):
        load_config(tmp_path)
