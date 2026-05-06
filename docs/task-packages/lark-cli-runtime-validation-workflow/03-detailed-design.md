# Detailed Design

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## RWP
选用并实现 `feishu_msg`。

- Workflow: `.harness/rwp/workflows/feishu_msg/workflow.md`
- Script: `.harness/rwp/workflows/feishu_msg/scripts/send.py`
- Shared Library: `.harness/rwp/libs/feishu_msg.py`
- Local Cache: `.harness/rwp/cache/lark-targets.json`
- Local Logs: `.harness/rwp/logs/feishu_msg/<run-id>/send-result.json`

## Script Interface
`send.py` 支持：

- `--text`: 要发送的文本。
- `--target`: 本地 target cache 中的目标名称。
- `--chat-id`: 临时指定飞书会话。
- `--user-id`: 临时指定飞书用户。
- `--as`: 发送身份，支持 `user` 和 `bot`。
- `--profile`: `lark-cli` profile，默认来自 `OPENRELAY_LARK_PROFILE`，否则为 `feishu-cli`。
- `--dry-run`: 只输出飞书 OpenAPI 请求，不真正发送。
- `--save-target`: 把当前 `chat_id` 或 `user_id` 保存为本地 target。
- `--set-default`: 保存 target 时设为默认目标。
- `--list-targets`: 列出本地 target cache。

## Local Configuration
`.harness/rwp/.env` 可选配置：

```env
OPENRELAY_LARK_PROFILE=feishu-cli
OPENRELAY_LARK_DEFAULT_TARGET=openrelay-p2p
OPENRELAY_LARK_TARGETS_FILE=.harness/rwp/cache/lark-targets.json
```

`lark-targets.json` 示例：

```json
{
  "default_target": "openrelay-p2p",
  "targets": {
    "openrelay-p2p": {
      "chat_id": "oc_xxx",
      "send_as": "user",
      "description": "OpenRelay 测试私聊会话"
    }
  }
}
```

## Verification Path
第一阶段验证：

1. `openharness rwp list` 能发现 `feishu_msg`。
2. `openharness rwp show feishu_msg` 能展示完整说明。
3. `uv run pytest tests/rwp/test_feishu_msg.py` 验证 target cache 和命令构造。
4. `openharness rwp run feishu_msg send.py --chat-id oc_dummy --text 'openrelay feishu_msg dry run' --dry-run --run-id feishu-msg-dry-run-test` 验证脚本外壳、`lark-cli` dry run 和日志写入。

## Failure Modes
- `lark-cli` 不存在：脚本返回非零退出码，并保留 stderr。
- target cache 缺失：脚本要求传入 `--target`、`--chat-id` 或 `--user-id`。
- target 同时包含 `chat_id` 和 `user_id`：脚本拒绝执行，避免目标语义不清。
- profile 授权失效：`lark-cli` 返回失败，日志保留原始输出。

## Follow-up
下一阶段在本 RWP 内增加 trace 冒烟脚本，例如 `trace_smoke.py`，复用 `send.py` 或共享库发送 `/status` 后查询 `~/.openrelay/data/openrelay.sqlite3`。
