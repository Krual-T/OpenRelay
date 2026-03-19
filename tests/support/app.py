from __future__ import annotations

from pathlib import Path

from openrelay.core import AppConfig, BackendConfig, FeishuConfig, IncomingMessage

_UNSET = object()


def make_app_config(
    tmp_path: Path,
    *,
    max_session_messages: int = 20,
    max_request_bytes: int = 1024,
    data_dir: Path | None = None,
    workspace_root: Path | None = None,
    main_workspace_dir: Path | None = None,
    develop_workspace_dir: Path | None = None,
    workspace_default_dir: Path | None | object = _UNSET,
    default_backend: str = "codex",
    default_safety_mode: str | None = None,
    default_model: str | None = None,
    codex_sessions_dir: Path | None = None,
    verify_token: str | None = "verify-token",
    bot_open_id: str | None = "ou_bot",
    connection_mode: str | None = None,
    allowed_open_ids: set[str] | None = None,
    admin_open_ids: set[str] | None = None,
    app_id: str = "app",
    app_secret: str = "secret",
    webhook_path: str = "/feishu/webhook",
    port: int = 3100,
) -> AppConfig:
    workspace_root = workspace_root or (tmp_path / "workspace")
    main_workspace_dir = main_workspace_dir or (tmp_path / "main")
    develop_workspace_dir = develop_workspace_dir or (tmp_path / "develop")
    data_dir = data_dir or (tmp_path / "data")
    codex_sessions_dir = codex_sessions_dir or (tmp_path / "native")

    backend_kwargs: dict[str, object] = {
        "default_backend": default_backend,
        "codex_sessions_dir": codex_sessions_dir,
    }
    if default_safety_mode is not None:
        backend_kwargs["default_safety_mode"] = default_safety_mode
    if default_model is not None:
        backend_kwargs["default_model"] = default_model

    feishu_kwargs: dict[str, object] = {
        "app_id": app_id,
        "app_secret": app_secret,
        "verify_token": verify_token,
        "bot_open_id": bot_open_id,
    }
    if allowed_open_ids is not None:
        feishu_kwargs["allowed_open_ids"] = allowed_open_ids
    if admin_open_ids is not None:
        feishu_kwargs["admin_open_ids"] = admin_open_ids
    if connection_mode is not None:
        feishu_kwargs["connection_mode"] = connection_mode

    config_kwargs: dict[str, object] = {
        "cwd": tmp_path,
        "port": port,
        "webhook_path": webhook_path,
        "data_dir": data_dir,
        "workspace_root": workspace_root,
        "main_workspace_dir": main_workspace_dir,
        "develop_workspace_dir": develop_workspace_dir,
        "max_request_bytes": max_request_bytes,
        "max_session_messages": max_session_messages,
        "feishu": FeishuConfig(**feishu_kwargs),
        "backend": BackendConfig(**backend_kwargs),
    }
    if workspace_default_dir is not _UNSET:
        config_kwargs["workspace_default_dir"] = workspace_default_dir
    return AppConfig(**config_kwargs)


def prepare_app_dirs(config: AppConfig, *, include_data_dir: bool = True) -> None:
    paths = [
        config.workspace_root,
        config.main_workspace_dir,
        config.develop_workspace_dir,
        config.backend.codex_sessions_dir,
    ]
    if include_data_dir:
        paths.insert(0, config.data_dir)
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def make_incoming_message(
    text: str,
    *,
    event_suffix: str = "",
    sender_open_id: str = "ou_user",
    actionable: bool = True,
    **overrides: str,
) -> IncomingMessage:
    suffix = event_suffix or text.replace(" ", "_")
    return IncomingMessage(
        event_id=f"evt_{suffix}",
        message_id=f"om_{suffix}",
        chat_id="oc_1",
        chat_type="p2p",
        sender_open_id=sender_open_id,
        text=text,
        actionable=actionable,
        **overrides,
    )
