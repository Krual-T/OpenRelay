from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / ".harness" / "rwp" / "libs" / "feishu_msg.py"


def load_module():
    spec = importlib.util.spec_from_file_location("feishu_msg_under_test", MODULE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_target_cache_round_trip(tmp_path: Path) -> None:
    feishu_msg = load_module()
    cache_path = tmp_path / "targets.json"
    target = feishu_msg.FeishuTarget(
        name="openrelay-p2p",
        send_as="user",
        chat_id="oc_test",
        description="test target",
    )

    feishu_msg.save_target(cache_path, target, set_default=True)
    resolved = feishu_msg.resolve_target(
        cache_path,
        name=None,
        chat_id=None,
        user_id=None,
        send_as=None,
    )

    assert resolved.name == "openrelay-p2p"
    assert resolved.chat_id == "oc_test"
    assert resolved.user_id is None
    assert resolved.send_as == "user"


def test_build_send_command_uses_cached_chat_target() -> None:
    feishu_msg = load_module()
    target = feishu_msg.FeishuTarget(name="openrelay-p2p", send_as="user", chat_id="oc_test")

    command = feishu_msg.build_send_command(
        profile="feishu-cli",
        target=target,
        text="/status smoke",
        idempotency_key="run-1",
        dry_run=True,
    )

    assert command == [
        "lark-cli",
        "im",
        "+messages-send",
        "--profile",
        "feishu-cli",
        "--as",
        "user",
        "--text",
        "/status smoke",
        "--idempotency-key",
        "run-1",
        "--chat-id",
        "oc_test",
        "--dry-run",
    ]
