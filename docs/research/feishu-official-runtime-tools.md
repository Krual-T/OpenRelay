# Feishu Official Runtime Tools Research

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Scope
本文件记录 OR-015 对飞书官方 CLI / 官方调试工具的调研结论。调研目标不是证明 openrelay 的真实 UI 已通过验收，而是判断官方工具能否协助真实飞书消息、卡片动作和流式卡片验证。

## Sources
- `larksuite/cli` README：<https://github.com/larksuite/cli>
- `lark-im` skill：<https://github.com/larksuite/cli/blob/main/skills/lark-im/SKILL.md>
- `lark-event` skill：<https://github.com/larksuite/cli/blob/main/skills/lark-event/SKILL.md>
- 飞书卡片搭建工具：<https://open.feishu.cn/cardkit>

## Findings
`lark-cli` 是 larksuite 团队维护的官方飞书 / Lark CLI。README 明确说明它覆盖即时通讯、事件订阅、OpenAPI 探索和通用调用，并提供面向 AI Agent 的 skills。

对 openrelay 有直接帮助的能力：

| Capability | Official Tool | Useful For OpenRelay | Limit |
| --- | --- | --- | --- |
| 发送测试消息 | `lark-cli im +messages-send` | 触发普通消息、命令消息、指定 chat 的 dry run | 需要安装 CLI、配置应用、授权 scope；本地当前未安装 `lark-cli` |
| 回复或创建消息 | `lark-cli im +messages-reply` | 构造 thread 场景，验证 reply 路由 | 只能证明消息 API 行为，不能证明 openrelay UI 卡片渲染正确 |
| 查询消息 | `lark-cli im +messages-mget`、`+chat-messages-list`、`+threads-messages-list`、`+messages-search` | 根据 `reply_message_id` 或 chat/thread 查询最终回复是否存在 | 对 interactive 卡片内容的结构化解释有限，不能替代客户端 UI 观察 |
| 监听事件 | `lark-cli event consume im.message.receive_v1` | 在真实飞书触发前后旁路确认消息事件是否进入飞书事件通道 | `lark-im` 文档说明 interactive 卡片事件在 compact conversion 中尚不支持，会返回 raw event data |
| 查看事件 schema | `lark-cli event schema <EventKey> --json` | 写稳定的事件过滤表达式，避免猜字段 | 只覆盖事件形状，不覆盖 UI 渲染结果 |
| 卡片设计预览 | 飞书卡片搭建工具 | 验证静态卡片 JSON 的结构和视觉预览 | 不是 openrelay 真实会话里的消息更新观测面 |

## Runtime UI Conclusion
官方 CLI 可以协助“真实运行验证”的前后两端：

- 触发端：用 `lark-cli im +messages-send` 发送测试命令或普通消息。
- 旁路观测端：用 `lark-cli event consume` 监听真实 IM 事件，用 `lark-cli im +messages-mget` 查询消息记录。

但本轮没有找到官方 CLI 能直接观测“用户客户端看到的真实 UI 状态”的证据。特别是流式卡片的关键问题是：飞书客户端是否按时间显示 CardKit streaming update、局部元素更新和最终卡片。这个结果仍需要人工看真实飞书客户端，系统侧再用 openrelay 本地 trace 与必要的飞书消息查询交叉判断。

因此 OR-015 的主验证路径应是：

1. 人工在真实飞书客户端触发和观察 UI。
2. 本地用 `openrelay-trace` 判断 openrelay runtime 是否执行正确分支。
3. 可选用 `lark-cli` 辅助发送测试消息、监听事件或查询消息存在性。
4. 不把 `lark-cli` 作为“流式 UI 已正确显示”的唯一证据。

## Suggested Commands
以下命令是后续安装并完成授权后的候选用法，当前不作为已执行证据：

```bash
lark-cli auth status
lark-cli im +messages-send --as user --chat-id "$OPENRELAY_TEST_CHAT_ID" --text "/status"
lark-cli event consume im.message.receive_v1 --max-events 1 --timeout 30s --as bot
lark-cli im +messages-mget --as bot --message-ids "$REPLY_MESSAGE_ID"
```

## Unknowns
- 是否存在官方命令能读取某张 CardKit 卡片的最新 JSON、streaming settings 或元素内容。本轮只确认 openrelay 代码会调用 CardKit update/settings/content API，没有确认官方 CLI 已封装这些查询能力。
- 飞书开放平台 API 调试台是否能稳定作为脚本化验收工具。本轮只把它视为人工排障入口，不纳入可执行验证矩阵。
- 真实客户端的流式渲染时间线无法仅靠服务端事件证明，需要人工观察或未来专门的 UI 自动化能力。
