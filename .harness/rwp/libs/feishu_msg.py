from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_TARGETS_FILE = ".harness/rwp/cache/lark-targets.json"


@dataclass(frozen=True)
class FeishuTarget:
    name: str
    send_as: str = "user"
    chat_id: str | None = None
    user_id: str | None = None
    description: str = ""

    @classmethod
    def from_mapping(cls, name: str, data: dict[str, Any]) -> "FeishuTarget":
        return cls(
            name=name,
            send_as=str(data.get("send_as") or "user"),
            chat_id=_optional_string(data.get("chat_id")),
            user_id=_optional_string(data.get("user_id")),
            description=str(data.get("description") or ""),
        )

    def to_mapping(self) -> dict[str, Any]:
        data: dict[str, Any] = {"send_as": self.send_as}
        if self.chat_id:
            data["chat_id"] = self.chat_id
        if self.user_id:
            data["user_id"] = self.user_id
        if self.description:
            data["description"] = self.description
        return data

    def validate(self) -> None:
        if bool(self.chat_id) == bool(self.user_id):
            raise ValueError("target must define exactly one of chat_id or user_id")
        if self.send_as not in {"user", "bot"}:
            raise ValueError("target send_as must be user or bot")


def resolve_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for path in (current, *current.parents):
        if (path / "AGENTS.md").exists() and (path / "pyproject.toml").exists():
            return path
    return Path.cwd().resolve()


def targets_file(repo_root: Path) -> Path:
    raw_path = os.environ.get("OPENRELAY_LARK_TARGETS_FILE") or DEFAULT_TARGETS_FILE
    return _resolve_path(repo_root, raw_path)


def load_targets(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"default_target": "", "targets": {}}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"target cache must be a JSON object: {path}")
    targets = data.setdefault("targets", {})
    if not isinstance(targets, dict):
        raise ValueError(f"target cache `targets` must be an object: {path}")
    data.setdefault("default_target", "")
    return data


def save_target(path: Path, target: FeishuTarget, *, set_default: bool = False) -> None:
    target.validate()
    data = load_targets(path)
    data["targets"][target.name] = target.to_mapping()
    if set_default or not data.get("default_target"):
        data["default_target"] = target.name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def list_target_names(path: Path) -> list[str]:
    data = load_targets(path)
    return sorted(str(name) for name in data["targets"].keys())


def resolve_target(
    path: Path,
    *,
    name: str | None,
    chat_id: str | None,
    user_id: str | None,
    send_as: str | None,
) -> FeishuTarget:
    if chat_id or user_id:
        target = FeishuTarget(
            name=name or "inline",
            send_as=send_as or "user",
            chat_id=chat_id,
            user_id=user_id,
        )
        target.validate()
        return target

    data = load_targets(path)
    target_name = name or os.environ.get("OPENRELAY_LARK_DEFAULT_TARGET") or data.get("default_target")
    if not target_name:
        raise ValueError(
            "no target specified; pass --target, --chat-id, --user-id, "
            "or set OPENRELAY_LARK_DEFAULT_TARGET"
        )
    target_data = data["targets"].get(target_name)
    if not isinstance(target_data, dict):
        raise ValueError(f"target not found in cache: {target_name}")
    target = FeishuTarget.from_mapping(str(target_name), target_data)
    if send_as:
        target = FeishuTarget(
            name=target.name,
            send_as=send_as,
            chat_id=target.chat_id,
            user_id=target.user_id,
            description=target.description,
        )
    target.validate()
    return target


def build_send_command(
    *,
    profile: str,
    target: FeishuTarget,
    text: str,
    idempotency_key: str,
    dry_run: bool,
) -> list[str]:
    target.validate()
    command = [
        "lark-cli",
        "im",
        "+messages-send",
        "--profile",
        profile,
        "--as",
        target.send_as,
        "--text",
        text,
        "--idempotency-key",
        idempotency_key,
    ]
    if target.chat_id:
        command.extend(["--chat-id", target.chat_id])
    else:
        command.extend(["--user-id", target.user_id or ""])
    if dry_run:
        command.append("--dry-run")
    return command


def parse_json_from_output(output: str) -> Any:
    stripped = output.strip()
    if not stripped:
        return None
    for index, char in enumerate(stripped):
        if char in "[{":
            try:
                return json.loads(stripped[index:])
            except json.JSONDecodeError:
                continue
    return None


def _resolve_path(repo_root: Path, raw_path: str) -> Path:
    expanded = Path(raw_path).expanduser()
    if expanded.is_absolute():
        return expanded
    return repo_root / expanded


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
