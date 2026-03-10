from __future__ import annotations

from dataclasses import dataclass, field
import json
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
    encrypt_key: str = ""
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
    codex_request_timeout_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class DirectoryShortcut:
    name: str
    path: str
    channels: tuple[str, ...] = ("all",)


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
    directory_shortcuts: tuple[DirectoryShortcut, ...] = ()


BOOL_TRUE = {"1", "true", "yes", "on"}
DIRECTORY_SHORTCUT_CHANNELS = {"all", "main", "develop"}


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


def read_optional_float(*names: str, default: float | None = None) -> float | None:
    raw = read_first(*names, default="")
    if raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else None



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


def _normalize_shortcut_channels(raw: str) -> tuple[str, ...]:
    tokens = [part.strip().lower() for part in raw.split(",") if part.strip()]
    if not tokens:
        return ("all",)
    if any(token not in DIRECTORY_SHORTCUT_CHANNELS for token in tokens):
        invalid = ", ".join(sorted({token for token in tokens if token not in DIRECTORY_SHORTCUT_CHANNELS}))
        raise ConfigError(f"Unsupported directory shortcut channel: {invalid}")
    if "all" in tokens:
        return ("all",)
    return tuple(dict.fromkeys(tokens))


def _shortcut_channels_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    if "all" in left or "all" in right:
        return True
    return bool(set(left) & set(right))


def read_directory_shortcuts(*names: str) -> tuple[DirectoryShortcut, ...]:
    raw = read_first(*names, default="")
    if not raw:
        return ()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError("DIRECTORY_SHORTCUTS must be valid JSON") from exc
    if not isinstance(payload, list):
        raise ConfigError("DIRECTORY_SHORTCUTS must be a JSON array")
    shortcuts: list[DirectoryShortcut] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ConfigError(f"DIRECTORY_SHORTCUTS[{index}] must be an object")
        name = str(item.get("name") or "").strip()
        path = str(item.get("path") or "").strip()
        channels = _normalize_shortcut_channels(str(item.get("channels") or item.get("channel") or "all"))
        if not name:
            raise ConfigError(f"DIRECTORY_SHORTCUTS[{index}] missing name")
        if not path:
            raise ConfigError(f"DIRECTORY_SHORTCUTS[{index}] missing path")
        next_shortcut = DirectoryShortcut(name=name, path=path, channels=channels)
        for existing in shortcuts:
            if existing.name == next_shortcut.name and _shortcut_channels_overlap(existing.channels, next_shortcut.channels):
                raise ConfigError(f"Duplicate directory shortcut name with overlapping channels: {name}")
        shortcuts.append(next_shortcut)
    return tuple(shortcuts)



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
            encrypt_key=read_first("FEISHU_ENCRYPT_KEY", default=""),
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
            codex_request_timeout_seconds=read_optional_float("CODEX_REQUEST_TIMEOUT_SECONDS", default=None),
        ),
        directory_shortcuts=read_directory_shortcuts("DIRECTORY_SHORTCUTS"),
    )
