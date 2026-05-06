---
name: feishu_msg
description: Send real Feishu messages for OpenRelay runtime validation through lark-cli, using local target cache.
---

# Feishu Message Runtime Workflow

## Purpose
`feishu_msg` 提供 openrelay 真实飞书验证的最小触发能力：用 `lark-cli` 向指定飞书会话发送一条真实消息，并把发送结果写入本地 RWP 日志。

## When To Use
当任务需要验证真实飞书入口、命令路由、消息 trace、回复链路或后续 runtime 行为时，先用本 workflow 发送测试消息。

## Prerequisites
- 本机已安装 `lark-cli`。
- `lark-cli profile list` 中存在隔离 profile，默认使用 `feishu-cli`。
- `.harness/rwp/.env` 可设置：
  - `OPENRELAY_LARK_PROFILE=feishu-cli`
  - `OPENRELAY_LARK_DEFAULT_TARGET=openrelay-p2p`
  - `OPENRELAY_LARK_TARGETS_FILE=.harness/rwp/cache/lark-targets.json`
- 本地 target cache 只保存 `chat_id` 或 `user_id` 等飞书标识，不保存 token、app secret 或 openrelay 服务应用凭据。

## Scripts
- `send.py`: 发送一条文本消息。支持从本地 target cache 读取目标，也支持用 `--chat-id` 或 `--user-id` 临时指定目标。

## Runtime Observation
运行后观察：
- `lark-cli` 退出码。
- stdout / stderr。
- `.harness/rwp/logs/feishu_msg/<run-id>/send-result.json`。
- 后续可用 `uv run openrelay-trace --db ~/.openrelay/data/openrelay.sqlite3 --message-id <message_id> --json` 查询 openrelay trace。

## Success Criteria
- `send.py --dry-run` 能构造正确的 `lark-cli im +messages-send` 请求。
- 非 dry run 时，`lark-cli` 成功返回，日志中保存发送结果和原始输出。
- 使用 target cache 时，调用方只需要指定 target 名称或使用默认 target，不需要重复输入 `chat_id`。

## Failure Evidence
失败时保留：
- 执行命令。
- 退出码。
- stdout / stderr。
- 解析到的 target 信息。
- 对应日志目录路径。

## Limitations
- 本 workflow 只负责发送真实飞书消息，不单独证明飞书客户端 UI 渲染正确。
- 本 workflow 不切换 `lark-cli` 默认 profile。
- 本 workflow 不使用 openrelay 服务应用凭据。

## Writeback Guidance
- `03-detailed-design.md`: 写入选用 `feishu_msg`、脚本名、目标 cache、profile 和预期证据。
- `04-verification.md`: 写入实际执行的 `openharness rwp run feishu_msg send.py ...` 命令、退出码、stdout / stderr 摘要。
- `05-evidence.md`: 写入日志目录、message id、openrelay trace 查询结果和残余风险。
