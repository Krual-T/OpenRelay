# Overview Design

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Selected Structure
第一阶段采用一个短名 RWP：`feishu_msg`。

它不是完整的真实运行测试平台，而是 openrelay 真实飞书验证的触发底座。后续 `/status` trace 冒烟、普通消息 turn 验证、`/resume` card action 验证，都应该复用这个底座发送消息，而不是每次重新拼 `lark-cli` 命令。

## Boundaries
覆盖范围：

- `.harness/rwp/workflows/feishu_msg/workflow.md` 作为 OpenHarness 可发现入口。
- `.harness/rwp/workflows/feishu_msg/scripts/send.py` 作为一键发送脚本。
- `.harness/rwp/libs/feishu_msg.py` 作为 target cache 和命令构造共享库。
- `.harness/rwp/cache/lark-targets.json` 作为本机 target cache，保持不提交。
- `.harness/rwp/logs/feishu_msg/` 作为本机运行日志，保持不提交。

不覆盖范围：

- 不自动切换或修改 `lark-cli` profile。
- 不保存凭据。
- 不宣称命令行查询可以证明飞书客户端流式 UI 正确。
- 不在第一阶段实现完整 `openrelay-trace` 自动判定。

## Main Flow
主流程是：

1. 调用方执行 `openharness rwp run feishu_msg send.py --text "<message>"`。
2. `send.py` 从 `.harness/rwp/.env` 和 target cache 解析 profile 与目标会话。
3. 脚本构造 `lark-cli im +messages-send` 命令。
4. 脚本执行命令并保存 stdout、stderr、退出码和解析结果。
5. 后续验证脚本或人工流程使用返回的 message id 查询 openrelay trace。

## Rejected Alternative
拒绝把 target 写死到脚本或 task package 文档中。原因是 `chat_id`、`user_id` 属于本机真实飞书环境配置，应该可缓存、可复用、可忽略提交，而不是成为仓库共享事实。
