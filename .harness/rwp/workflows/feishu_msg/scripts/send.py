from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

RWP_ROOT = Path(__file__).resolve().parents[3]
LIBS_ROOT = RWP_ROOT / "libs"
sys.path.insert(0, str(LIBS_ROOT))

from feishu_msg import (  # noqa: E402
    FeishuTarget,
    build_send_command,
    list_target_names,
    parse_json_from_output,
    resolve_repo_root,
    resolve_target,
    save_target,
    targets_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a Feishu message through lark-cli.")
    parser.add_argument("--text", help="要发送的文本消息。")
    parser.add_argument("--target", help="本地 target cache 中的目标名称。")
    parser.add_argument("--chat-id", help="临时指定飞书 chat_id，形如 oc_xxx。")
    parser.add_argument("--user-id", help="临时指定飞书 user open_id，形如 ou_xxx。")
    parser.add_argument("--as", dest="send_as", choices=("user", "bot"), help="发送身份。")
    parser.add_argument("--profile", default=os.environ.get("OPENRELAY_LARK_PROFILE", "feishu-cli"))
    parser.add_argument("--dry-run", action="store_true", help="只打印 lark-cli 请求，不真正发送。")
    parser.add_argument("--run-id", help="本次运行标识；默认自动生成。")
    parser.add_argument("--save-target", help="把 --chat-id 或 --user-id 保存为指定 target 名称。")
    parser.add_argument("--set-default", action="store_true", help="保存 target 时同时设为默认目标。")
    parser.add_argument("--description", default="", help="保存 target 时写入的说明。")
    parser.add_argument("--list-targets", action="store_true", help="列出本地 target cache 中的目标。")
    args = parser.parse_args()

    repo_root = resolve_repo_root()
    cache_path = targets_file(repo_root)

    if args.list_targets:
        print(json.dumps({"targets_file": str(cache_path), "targets": list_target_names(cache_path)}, ensure_ascii=False, indent=2))
        return 0

    if args.save_target:
        target = FeishuTarget(
            name=args.save_target,
            send_as=args.send_as or "user",
            chat_id=args.chat_id,
            user_id=args.user_id,
            description=args.description,
        )
        save_target(cache_path, target, set_default=args.set_default)
        print(json.dumps({"saved_target": target.name, "targets_file": str(cache_path)}, ensure_ascii=False, indent=2))
        if not args.text:
            return 0

    if not args.text:
        print("ERROR: --text is required unless --list-targets or --save-target without sending is used", file=sys.stderr)
        return 2

    run_id = args.run_id or f"feishu-msg-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    idempotency_key = run_id
    target = resolve_target(
        cache_path,
        name=args.target or args.save_target,
        chat_id=args.chat_id,
        user_id=args.user_id,
        send_as=args.send_as,
    )
    command = build_send_command(
        profile=args.profile,
        target=target,
        text=args.text,
        idempotency_key=idempotency_key,
        dry_run=args.dry_run,
    )

    completed = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    parsed_stdout = parse_json_from_output(completed.stdout)
    result = {
        "run_id": run_id,
        "targets_file": str(cache_path),
        "target": target.to_mapping() | {"name": target.name},
        "profile": args.profile,
        "dry_run": args.dry_run,
        "returncode": completed.returncode,
        "command": command,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "parsed_stdout": parsed_stdout,
    }

    log_dir = repo_root / ".harness" / "rwp" / "logs" / "feishu_msg" / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    result_path = log_dir / "send-result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({"run_id": run_id, "returncode": completed.returncode, "result_path": str(result_path)}, ensure_ascii=False, indent=2))
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="" if completed.stderr.endswith("\n") else "\n")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
