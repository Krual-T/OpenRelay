from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable

from openrelay.config import AppConfig
from openrelay.models import SessionRecord
from openrelay.release import infer_release_channel
from openrelay.state import StateStore


@dataclass(slots=True)
class NativeSessionSummary:
    session_id: str
    cwd: str
    updated_at: str
    file_path: str
    label: str
    first_user_message: str
    matches_workspace: bool
    release_channel: str



def _normalize_inline(text: object) -> str:
    return " ".join(str(text or "").split()).strip()



def _shorten(text: object, max_length: int = 42) -> str:
    value = _normalize_inline(text)
    if len(value) <= max_length:
        return value
    return f"{value[:max_length - 3]}..."



def _walk_files(root_dir: Path) -> Iterable[Path]:
    if not root_dir.exists():
        return []
    return root_dir.rglob("*.jsonl")



def _read_first_line(file_path: Path) -> str:
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            return handle.readline().strip()
    except Exception:
        return ""



def _read_first_user_message(file_path: Path) -> str:
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                parsed = json.loads(line)
                if parsed.get("type") == "event_msg" and parsed.get("payload", {}).get("type") == "user_message":
                    message = _normalize_inline(parsed.get("payload", {}).get("message"))
                    if message:
                        return message
    except Exception:
        return ""
    return ""



def _summarize_label(session_id: str, first_user_message: str, cwd: str, file_path: Path) -> str:
    if first_user_message:
        return _shorten(first_user_message, 42)
    folder = Path(cwd).name.strip() if cwd else file_path.parent.name.strip()
    if folder:
        return _shorten(folder, 42)
    return session_id or file_path.stem



def _read_session_meta(config: AppConfig, file_path: Path) -> NativeSessionSummary | None:
    line = _read_first_line(file_path)
    if not line:
        return None
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError:
        return None
    if parsed.get("type") != "session_meta" or not parsed.get("payload", {}).get("id"):
        return None
    payload = parsed.get("payload", {})
    session_id = str(payload.get("id"))
    cwd = str(payload.get("cwd") or "")
    first_user_message = _read_first_user_message(file_path)
    matches_workspace = False
    if cwd:
        try:
            roots = [config.workspace_root.resolve(), config.main_workspace_dir.resolve(), config.develop_workspace_dir.resolve()]
            cwd_path = Path(cwd).resolve()
            matches_workspace = any(cwd_path == root or root in cwd_path.parents for root in roots)
        except Exception:
            matches_workspace = False
    temp_session = SessionRecord(session_id=session_id, base_key="", backend="codex", cwd=cwd, release_channel="")
    return NativeSessionSummary(
        session_id=session_id,
        cwd=cwd,
        updated_at=str(parsed.get("timestamp") or payload.get("timestamp") or ""),
        file_path=str(file_path),
        label=_summarize_label(session_id, first_user_message, cwd, file_path),
        first_user_message=_shorten(first_user_message, 72),
        matches_workspace=matches_workspace,
        release_channel=infer_release_channel(config, temp_session),
    )



def list_native_sessions(config: AppConfig, limit: int = 20, cwd_prefix: str = "") -> list[NativeSessionSummary]:
    entries = []
    for file_path in _walk_files(config.backend.codex_sessions_dir):
        entry = _read_session_meta(config, file_path)
        if entry is None:
            continue
        if cwd_prefix and not entry.cwd.startswith(cwd_prefix):
            continue
        entries.append(entry)
    deduped: list[NativeSessionSummary] = []
    seen: set[str] = set()
    for entry in sorted(entries, key=lambda item: item.updated_at, reverse=True):
        if entry.session_id in seen:
            continue
        seen.add(entry.session_id)
        deduped.append(entry)
    deduped.sort(key=lambda item: (item.matches_workspace, item.updated_at), reverse=True)
    return deduped[:limit]



def find_native_session(config: AppConfig, session_id: str) -> NativeSessionSummary | None:
    target = session_id.strip()
    if not target:
        return None
    for file_path in _walk_files(config.backend.codex_sessions_dir):
        entry = _read_session_meta(config, file_path)
        if entry is None:
            continue
        if entry.session_id == target or entry.session_id.startswith(target) or target in Path(entry.file_path).stem:
            return entry
    return None



def import_native_session(store: StateStore, base_key: str, native_session: NativeSessionSummary, current_session: SessionRecord) -> SessionRecord:
    imported = SessionRecord(
        session_id=native_session.session_id,
        base_key=base_key,
        backend=current_session.backend,
        cwd=native_session.cwd or current_session.cwd,
        label=native_session.label or current_session.label,
        model_override=current_session.model_override,
        safety_mode=current_session.safety_mode,
        native_session_id=native_session.session_id,
        release_channel=native_session.release_channel or current_session.release_channel,
    )
    return store.save_session(imported)
