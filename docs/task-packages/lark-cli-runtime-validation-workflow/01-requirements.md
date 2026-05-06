# Requirements

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Intent
本任务的意图是在 openrelay 这个具体项目里，整理一条项目专属的 runtime 级验证路径。

openrelay 的关键行为发生在真实飞书入口、消息事件、机器人回复、会话绑定、流式卡片和本地 runtime 编排之间。过去很多验证需要维护者手动打开飞书客户端、发送消息、点击卡片、观察回复，再结合本地日志或 SQLite 记录判断是否通过。

现在希望把这类验证从“人工经验步骤”沉淀为“可重复执行的项目级 runtime 工作流”。`lark-cli` 是当前可用于自动化部分飞书操作和观测的工具样例，但它不是测试框架本身，也不是 openrelay runtime 验证的唯一入口。

## Purpose
本包要回答的是 openrelay 自己的问题：

- 哪些行为不能只靠 `pytest` 证明，需要真实或近真实 runtime 验证。
- 哪些真实飞书验证步骤过去依赖人工客户端操作。
- 哪些步骤可以借助 `lark-cli` 自动化，哪些仍然需要人工观察或其他观测面补充。
- 这套流程最终应该如何被 agent 发现、执行和汇报。

## Relationship To OpenHarness
本包不负责设计 openharness 的通用可插拔机制。

本包负责提供一个真实项目样例：openrelay 如何把自己的飞书 runtime 验证需求整理出来，并尝试用 `lark-cli` 让其中一部分流程自动化。后续 `../openharness` 中的通用机制可以从这个样例中抽象，但不要在本包里提前把项目细节泛化成框架设计。

## Non-Goals
- 不把 `lark-cli` 定义为唯一测试方式。
- 不用 `lark-cli` 替代 `pytest`。
- 不在本包里设计 openharness 的通用 adapter、plugin 或 skill-hub 架构。
- 不提前承诺所有真实飞书 UI 行为都能被命令行完全自动判定。

## First Slice
第一阶段先解决“发送一条真实飞书消息太繁琐”的问题，而不是直接实现完整 runtime 验证矩阵自动判定。

- 目标用户：维护 openrelay 真实飞书链路的开发者和 agent。
- 核心场景：调用方只提供要发送的消息文本，脚本从本地 target cache 读取默认飞书会话，并通过隔离的 `feishu-cli` profile 调用 `lark-cli` 发送消息。
- 单一成功指标：可以执行 `openharness rwp run feishu_msg send.py --text "<message>"`，在不重复输入 `chat_id` 的情况下完成发送流程；缺少本地缓存时，也能用 `--chat-id` 或 `--user-id` 完成 dry run。
- 本轮非目标：不自动判定流式卡片 UI 是否正确；不保存 token、app secret 或 openrelay 服务应用配置；不切换 `lark-cli` 默认 profile。
- 反例：只在聊天里记录一串 `lark-cli im +messages-send` 命令，但没有 RWP、没有 target cache、没有日志产物。这也能手动发消息，但不能成为可复用 runtime workflow。

## Acceptance Criteria
- `openharness rwp list` 能发现 `feishu_msg`。
- `openharness rwp show feishu_msg` 能说明用途、前置条件、脚本、证据和限制。
- `send.py` 支持 `--text`、`--target`、`--chat-id`、`--user-id`、`--as`、`--profile`、`--dry-run`。
- `send.py` 支持 `--save-target` 和 `--list-targets`，本地 target cache 默认写入 `.harness/rwp/cache/lark-targets.json`。
- RWP 日志写入 `.harness/rwp/logs/feishu_msg/<run-id>/send-result.json`，并且这些本地运行产物不会被提交。
