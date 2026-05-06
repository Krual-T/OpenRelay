# Verification

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Latest Result
2026-05-07：第一阶段 dry run 通过。

已执行：

- `openharness rwp list`
  - 结果：能发现 `feishu_msg`。
- `openharness rwp show feishu_msg`
  - 结果：能展示 workflow 详情。
- `uv run pytest tests/rwp/test_feishu_msg.py`
  - 结果：2 passed。
- `openharness rwp run feishu_msg send.py --chat-id oc_dummy --text 'openrelay feishu_msg dry run' --dry-run --run-id feishu-msg-dry-run-test`
  - 结果：退出码 0，生成 dry run OpenAPI 请求，日志写入 `.harness/rwp/logs/feishu_msg/feishu-msg-dry-run-test/send-result.json`。
- `openharness rwp run feishu_msg send.py --save-target openrelay-dummy --chat-id oc_dummy --set-default --description 'dummy dry run target'`
  - 结果：退出码 0，target cache 写入 `.harness/rwp/cache/lark-targets.json`。
- `openharness rwp run feishu_msg send.py --target openrelay-dummy --text 'openrelay feishu_msg cached target dry run' --dry-run --run-id feishu-msg-cached-target-dry-run-final`
  - 结果：退出码 0，脚本从 target cache 读取 `openrelay-dummy` 并生成 dry run OpenAPI 请求。

## Current Coverage
已覆盖：

- RWP 可发现性。
- `send.py` dry run。
- 本地 target cache 读写逻辑。
- 使用 target 名称发送消息的 dry run。
- `lark-cli im +messages-send` 命令构造。
- 本地日志写入。

尚未覆盖：

- 真实发送到 OpenRelay 测试会话。
- 从真实 `message_id` 查询 openrelay trace。
- 流式卡片 UI 人工观察。
