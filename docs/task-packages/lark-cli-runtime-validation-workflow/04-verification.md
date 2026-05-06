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
- `openharness rwp run feishu_msg send.py --chat-id oc_dummy --text 'logger dry run' --dry-run --run-id feishu-msg-logger-dry-run`
  - 结果：初次失败，原因是当前项目 `uv run python` 环境无法 import `openharness.rwp`。
- `openharness rwp run feishu_msg send.py --chat-id oc_dummy --text 'logger dry run' --dry-run --run-id feishu-msg-logger-dry-run-2`
  - 结果：曾通过 fallback logger 临时恢复；随后按用户要求移除 fallback，把根因修到 OpenHarness 源仓库。
- OpenHarness 源仓库 `b0908ab Expose RWP runtime API to workflow scripts`
  - 结果：修复 `openharness rwp run`，向 RWP 子进程注入 runtime API 路径；已 push 到 `origin/main`，并在 openrelay 中执行 `openharness update`。
- `openharness rwp run feishu_msg send.py --chat-id oc_dummy --text 'openharness runtime api import after update' --dry-run --run-id feishu-msg-runtime-api-after-update`
  - 结果：退出码 0；`send.py` 已无 fallback，直接导入 `from openharness.rwp import get_logger`，通过更新后的 OpenHarness 外壳正常运行。
- `openharness rwp run feishu_msg send.py --save-target openrelay-p2p --chat-id 'oc_7bea2cfa55a47c1d33fb0fdc607153f2' --set-default --description 'OpenRelay P2P real runtime validation chat'`
  - 结果：退出码 0，真实 OpenRelay P2P target 写入本地 target cache。
- `openharness rwp run feishu_msg send.py --target openrelay-p2p --text '/status OR-021 feishu_msg real run 20260506T163640Z' --run-id feishu-msg-real-status-20260506T163640Z`
  - 结果：退出码 0，真实飞书消息发送成功，message id 为 `om_x100b5082af207ca8c2ed58906b4e7b3`。
- `uv run openrelay-trace --db ~/.openrelay/data/openrelay.sqlite3 --message-id om_x100b5082af207ca8c2ed58906b4e7b3 --json`
  - 结果：查到 `ingress.message.received`、`session.key.resolved`、`session.loaded`、`dispatch.command.detected`、`reply.sent`，reply id 为 `om_x100b5082accc7ca8c2b297e33e4fc87`。

## Current Coverage
已覆盖：

- RWP 可发现性。
- `send.py` dry run。
- 本地 target cache 读写逻辑。
- 使用 target 名称发送消息的 dry run。
- 使用真实 OpenRelay P2P target 发送 `/status`。
- 用真实运行库查询发送消息对应的 openrelay trace。
- `lark-cli im +messages-send` 命令构造。
- 本地日志写入。

尚未覆盖：

- 流式卡片 UI 人工观察。
