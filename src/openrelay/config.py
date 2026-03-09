from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os


SAFETY_MODES = {"read-only", "workspace-write", "danger-full-access"}
GROUP_SCOPES = {"sender", "shared"}
BACKEND_ALIASES = {
    "codex": "codex",
    "codex-cli": "codex",
    "claude": "claude",
    "claude-cli": "claude",
}


@dataclass(slots=True)
class FeishuConfig:
    app_id: str
    app_secret: str
    verify_token: str = ""
    bot_open_id: str = ""
    connection_mode: str = "webhook"
    stream_mode: str = "off"
    group_reply_all: bool = False
    group_session_scope: str = "sender"
    allowed_open_ids: set[str] = field(default_factory=set)
    admin_open_ids: set[str] = field(default_factory=set)


@dataclass(slots=True)
class BackendConfig:
    default_backend: str = "codex"
    default_model: str = ""
    default_safety_mode: str = "workspace-write"
    codex_cli_path: str = "codex"
    codex_sessions_dir: Path = Path.home() / ".codex" / "sessions"


@dataclass(slots=True)
class AppConfig:
    cwd: Path
    port: int
    webhook_path: str
    data_dir: Path
    workspace_root: Path
    main_workspace_dir: Path
    develop_workspace_dir: Path
    max_request_bytes: int
    max_session_messages: int
    feishu: FeishuConfig
    backend: BackendConfig


BOOL_TRUE = {"1", "true", "yes", "on"}


class ConfigError(RuntimeError):
    pass



def load_env_file(cwd: Path) -> None:
    env_path = cwd / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        if os.environ.get(key, "") == "":
            os.environ[key] = value



def read_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in BOOL_TRUE



def read_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))



def read_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip() != "":
            return value.strip()
    return default



def read_csv(*names: str) -> set[str]:
    raw = read_first(*names, default="")
    return {item.strip() for item in raw.split(",") if item.strip()}



def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required env: {name}")
    return value



def normalize_backend_name(value: str) -> str:
    normalized = value.strip().lower()
    mapped = BACKEND_ALIASES.get(normalized)
    if mapped:
        return mapped
    raise ConfigError(f"Unsupported backend: {value}")



def resolve_env_path(base: Path, *names: str, default: str = "") -> Path:
    raw = read_first(*names, default=default)
    return (base / raw).resolve() if raw else base.resolve()



def load_config(cwd: str | Path | None = None) -> AppConfig:
    base = Path(cwd or os.getcwd()).resolve()
    load_env_file(base)

    workspace_root = resolve_env_path(base, "WORKSPACE_ROOT", "WORKSPACE_DIR", default=".")
    main_workspace_dir = resolve_env_path(base, "MAIN_WORKSPACE_DIR", "STABLE_WORKSPACE_DIR", default=str(workspace_root))
    develop_workspace_dir = resolve_env_path(base, "DEVELOP_WORKSPACE_DIR", default=str(workspace_root))
    data_dir = resolve_env_path(base, "DATA_DIR", default="./data")

    default_backend = normalize_backend_name(read_first("DEFAULT_BACKEND", "MODEL_BACKEND", default="codex"))
    default_model = read_first("DEFAULT_MODEL", "CODEX_MODEL_OVERRIDE", "MODEL_NAME", default="")
    default_safety_mode = read_first("DEFAULT_SAFETY_MODE", "CODEX_SANDBOX", default="workspace-write").lower()
    if default_safety_mode not in SAFETY_MODES:
        raise ConfigError(f"Unsupported safety mode: {default_safety_mode}")
    group_scope = read_first("FEISHU_GROUP_SESSION_SCOPE", default="sender").lower()
    if group_scope not in GROUP_SCOPES:
        raise ConfigError(f"Unsupported FEISHU_GROUP_SESSION_SCOPE: {group_scope}")

    return AppConfig(
        cwd=base,
        port=read_int("PORT", 3000, 1, 65535),
        webhook_path=read_first("WEBHOOK_PATH", default="/feishu/webhook"),
        data_dir=data_dir,
        workspace_root=workspace_root,
        main_workspace_dir=main_workspace_dir,
        develop_workspace_dir=develop_workspace_dir,
        max_request_bytes=read_int("MAX_REQUEST_BYTES", 1024 * 1024, 1024, 16 * 1024 * 1024),
        max_session_messages=read_int("MAX_SESSION_MESSAGES", 20, 2, 200),
        feishu=FeishuConfig(
            app_id=require_env("FEISHU_APP_ID"),
            app_secret=require_env("FEISHU_APP_SECRET"),
            verify_token=read_first("FEISHU_VERIFY_TOKEN", default=""),
            bot_open_id=read_first("FEISHU_BOT_OPEN_ID", default=""),
            connection_mode=read_first("FEISHU_CONNECTION_MODE", default="websocket").lower(),
            stream_mode=read_first("FEISHU_STREAM_MODE", default="card").lower(),
            group_reply_all=read_bool("FEISHU_GROUP_REPLY_ALL", False),
            group_session_scope=group_scope,
            allowed_open_ids=read_csv("FEISHU_ALLOWED_OPEN_IDS"),
            admin_open_ids=read_csv("FEISHU_ADMIN_OPEN_IDS"),
        ),
        backend=BackendConfig(
            default_backend=default_backend,
            default_model=default_model,
            default_safety_mode=default_safety_mode,
            codex_cli_path=read_first("CODEX_CLI_PATH", "CODEX_PATH", default="codex"),
            codex_sessions_dir=Path(read_first("CODEX_SESSIONS_DIR", default=str(Path.home() / ".codex" / "sessions"))).expanduser().resolve(),
        ),
    )
