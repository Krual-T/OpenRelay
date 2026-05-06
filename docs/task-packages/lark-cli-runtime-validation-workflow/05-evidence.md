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

## Artifacts
- `.harness/rwp/logs/feishu_msg/feishu-msg-dry-run-test/send-result.json`
- `.harness/rwp/logs/feishu_msg/feishu-msg-cached-target-dry-run-final/send-result.json`

该 artifact 是本地运行产物，按 `.gitignore` 规则不提交。

## Residual Risks
- 当前只完成 dry run，尚未用真实 OpenRelay 测试会话发送消息。
- 当前没有自动解析返回 message id 后查询 `openrelay-trace`。
- `lark-cli` 不能单独证明飞书客户端 UI 渲染正确，后续仍需结合人工观察或其他观测面。
