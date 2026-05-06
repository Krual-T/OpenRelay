# Evidence

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Files
- `.harness/rwp/workflows/feishu_msg/workflow.md`
- `.harness/rwp/workflows/feishu_msg/scripts/send.py`
- `.harness/rwp/libs/feishu_msg.py`
- `tests/rwp/test_feishu_msg.py`
- `.gitignore`
- `.harness/.gitignore`

## Commands
- `openharness init`
- `openharness rwp list`
- `openharness rwp show feishu_msg`
- `uv run pytest tests/rwp/test_feishu_msg.py`
- `openharness rwp run feishu_msg send.py --chat-id oc_dummy --text 'openrelay feishu_msg dry run' --dry-run --run-id feishu-msg-dry-run-test`
- `openharness rwp run feishu_msg send.py --save-target openrelay-dummy --chat-id oc_dummy --set-default --description 'dummy dry run target'`
- `openharness rwp run feishu_msg send.py --list-targets`
- `openharness rwp run feishu_msg send.py --target openrelay-dummy --text 'openrelay feishu_msg cached target dry run' --dry-run --run-id feishu-msg-cached-target-dry-run-final`
- `openharness rwp run feishu_msg send.py --chat-id oc_dummy --text 'logger dry run' --dry-run --run-id feishu-msg-logger-dry-run`
- `openharness rwp run feishu_msg send.py --chat-id oc_dummy --text 'logger dry run' --dry-run --run-id feishu-msg-logger-dry-run-2`
- OpenHarness 源仓库提交并推送：`b0908ab Expose RWP runtime API to workflow scripts`
- `openharness update`
- `openharness rwp run feishu_msg send.py --chat-id oc_dummy --text 'openharness runtime api import after update' --dry-run --run-id feishu-msg-runtime-api-after-update`
- `lark-cli doctor --profile feishu-cli`
- `openharness rwp run feishu_msg send.py --save-target openrelay-p2p --chat-id 'oc_7bea2cfa55a47c1d33fb0fdc607153f2' --set-default --description 'OpenRelay P2P real runtime validation chat'`
- `openharness rwp run feishu_msg send.py --target openrelay-p2p --text '/status OR-021 feishu_msg real run 20260506T163640Z' --run-id feishu-msg-real-status-20260506T163640Z`
- `uv run openrelay-trace --db ~/.openrelay/data/openrelay.sqlite3 --message-id om_x100b5082af207ca8c2ed58906b4e7b3 --json`

## Artifacts
- `.harness/rwp/logs/feishu_msg/feishu-msg-dry-run-test/send-result.json`
- `.harness/rwp/logs/feishu_msg/feishu-msg-cached-target-dry-run-final/send-result.json`
- `.harness/rwp/logs/feishu_msg/feishu-msg-logger-dry-run-2/send-result.json`
- `.harness/rwp/logs/feishu_msg/feishu-msg-runtime-api-after-update/send-result.json`
- `.harness/rwp/logs/feishu_msg/feishu-msg-real-status-20260506T163640Z/send-result.json`
- `~/.openrelay/data/openrelay.sqlite3` 中 message id `om_x100b5082af207ca8c2ed58906b4e7b3` 对应 trace。

该 artifact 是本地运行产物，按 `.gitignore` 规则不提交。

## Residual Risks
- 当前已完成一条真实 `/status` 发送和 trace 查询，但还没有把 trace 查询自动并入 `send.py`。
- `lark-cli` 不能单独证明飞书客户端 UI 渲染正确，后续仍需结合人工观察或其他观测面。
- 直接执行 `uv run python -c 'import openharness'` 在 openrelay 项目环境中仍会失败，这是预期边界；只有通过 `openharness rwp run` 启动的 RWP 子进程会获得 OpenHarness runtime API 路径。
