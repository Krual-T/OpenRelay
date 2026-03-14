from __future__ import annotations

import json
from pathlib import Path

from openrelay.core.config import AppConfig
from openrelay.core.models import SessionRecord, utc_now


RELEASE_CHANNELS = {"main", "develop"}



def normalize_release_channel(value: str | None, fallback: str = "main") -> str:
    normalized = (value or "").strip().lower()
    if normalized in RELEASE_CHANNELS:
        return normalized
    return fallback



def get_release_workspace(config: AppConfig, channel: str = "main") -> Path:
    normalized = normalize_release_channel(channel, "main")
    return config.main_workspace_dir if normalized == "main" else config.develop_workspace_dir



def infer_release_channel(config: AppConfig, session: SessionRecord | None = None) -> str:
    if session and session.release_channel:
        return normalize_release_channel(session.release_channel, "main")
    cwd = Path(session.cwd).resolve() if session and session.cwd else config.workspace_root.resolve()
    main_root = config.main_workspace_dir.resolve()
    develop_root = config.develop_workspace_dir.resolve()
    if cwd == main_root or main_root in cwd.parents:
        return "main"
    if cwd == develop_root or develop_root in cwd.parents:
        return "develop"
    return "main"



def get_session_workspace_root(config: AppConfig, session: SessionRecord | None = None) -> Path:
    return get_release_workspace(config, infer_release_channel(config, session))



def format_release_channel(channel: str) -> str:
    return "main（稳定）" if normalize_release_channel(channel, "main") == "main" else "develop（修复）"



def build_release_session_label(channel: str) -> str:
    return "main 稳定版" if normalize_release_channel(channel, "main") == "main" else "develop 修复版"



def release_log_path(config: AppConfig) -> Path:
    return config.data_dir / "release-events.jsonl"



def append_release_event(config: AppConfig, payload: dict[str, object]) -> dict[str, object]:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    event = {"timestamp": payload.get("timestamp") or utc_now(), **payload}
    with release_log_path(config).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event



def read_release_events(config: AppConfig, session_key: str = "", limit: int = 10) -> list[dict[str, object]]:
    path = release_log_path(config)
    if not path.exists():
        return []
    events: list[dict[str, object]] = []
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if session_key and event.get("session_key") != session_key:
            continue
        events.append(event)
        if len(events) >= limit:
            break
    return events



def summarize_release_event(event: dict[str, object] | None) -> str:
    if not event:
        return ""
    timestamp = str(event.get("timestamp") or "")
    stamp = timestamp[5:16].replace("T", " ") if len(timestamp) >= 16 else timestamp
    source = format_release_channel(str(event.get("from_channel") or "main")) if event.get("from_channel") else "未知通道"
    target = format_release_channel(str(event.get("to_channel") or "main"))
    reason = str(event.get("reason") or "").strip()
    return f"{stamp} 从 {source} 切到 {target}{f'：{reason}' if reason else ''}"



def build_release_switch_note(event: dict[str, object]) -> str:
    timestamp = str(event.get("timestamp") or "")
    lines = [
        f"系统记录（{timestamp[:16].replace('T', ' ')}）",
        f"已从 {format_release_channel(str(event.get('from_channel') or 'main')) if event.get('from_channel') else '未知通道'} 切换到 {format_release_channel(str(event.get('to_channel') or 'main'))}。",
    ]
    if event.get("command"):
        lines.append(f"触发命令：{event['command']}")
    if event.get("reason"):
        lines.append(f"触发原因：{event['reason']}")
    if event.get("previous_session_id"):
        lines.append(f"上一会话：{event['previous_session_id']}")
    if event.get("previous_cwd"):
        lines.append(f"上一目录：{event['previous_cwd']}")
    if event.get("cancelled_active_run"):
        lines.append("切换前已中断上一条进行中的回复。")
    if normalize_release_channel(str(event.get("to_channel") or "main"), "main") == "main":
        lines.append("后续智能体请先确认 main 可稳定运行，再回 develop 修复问题。")
    else:
        lines.append("后续智能体请基于这条系统记录继续修复问题，并在必要时切回 main 验证稳定版本。")
    return "\n".join(lines)
