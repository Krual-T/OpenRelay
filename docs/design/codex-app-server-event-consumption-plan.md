# Codex App-Server Typed Contract 适配设计

更新时间：2026-03-17

## 目标

把 `openrelay` 的 Codex 适配基线收敛到一条清晰主线：

- 只支持官方 `codex >= 0.115.0`
- 只支持 external `codex app-server`
- 只消费 typed contract
- 不再把 external `codex/event/*` legacy 通知当正式输入面

这份文档回答三个问题：

1. 现在正式支持哪些消息。
2. 每条消息属于渲染、系统、忽略还是仅观察。
3. unknown event 应该怎么兜底，避免再次出现漏接后直接卡死或静默丢失。

## 支持边界

### 正式支持

- `codex app-server` 外部进程协议
- typed notification / typed server request
- `item/*`、`turn/*`、`thread/*`、`account/*`、`skills/*` 等 typed 方法

### 明确不再支持

- external `codex/event/*` legacy 通知
- `v1 / v2` 双轨正式兼容
- `hybrid` 运行模式
- 旧版 `app_server.py` 里的并行 turn 消费路径

这些旧路径已经从适配主实现中删除；如果外部 transport 未来再次出现未知方法，会走 observe 兜底，而不是重新引入第二套消费链。

## 当前消费链路

```text
CodexTurnStream
  -> CodexProtocolMapper.map_notification()
  -> CodexEventRegistry.lookup()
  -> CodexSemanticMapper.map()
  -> CodexRuntimeEventProjector.project()
  -> AgentRuntime reducer / presenter
```

职责边界如下：

- `app_server.py`：只负责 app-server 进程、RPC、transport 分发。
- `turn_stream.py`：负责单轮流式消费、server request 闭环、notification 分发。
- `event_registry.py`：声明 typed method 到统一语义的注册表。
- `semantic_mapper.py`：把 raw payload 收敛成稳定语义事件。
- `runtime_projector.py`：把语义事件投影成 `RuntimeEvent`。
- `agent_runtime/reducer.py`：消费统一运行时事件，不理解 provider method。

## 处理原则

### 1. 先统一语义，再做业务处理

主路径不直接围绕 `item.type`、原始 method 名或旧别名写分支，而是统一成稳定语义：

- `assistant.delta`
- `reasoning.delta`
- `plan.updated`
- `tool.progress`
- `turn.terminal`
- `thread.status.changed`
- `account.rate_limits.updated`

### 2. 每条消息都必须有去向

观察到的消息必须落入四类之一：

- `render`：进入 transcript / live turn 展示
- `system`：推进运行时状态，但不一定直接展示
- `ignore`：明确知道是中间态或回声，不进入主路径
- `observe`：暂未纳入正式状态机，但保留完整原始 payload

### 3. unknown event 不允许静默丢失

对于未注册 method、未识别 item type、或已注册但当前无法安全归类的 payload：

- 生成 observe notice
- 保留原始 method 和完整 payload
- 进入 runtime 的 backend event 列表
- 允许 Feishu / 调试面直接看到内容

这就是当前实现里的“兜底消费”：不是把它当正式语义处理，而是“完整展示并留痕”。

## 事件矩阵

### 渲染事件

| method | 统一语义 | 作用 |
| --- | --- | --- |
| `item/agentMessage/delta` | `assistant.delta` | assistant 正文流式增量 |
| `item/reasoning/textDelta` | `reasoning.delta` | 推理正文增量 |
| `item/reasoning/summaryTextDelta` | `reasoning.delta` | 推理摘要增量 |
| `item/plan/delta` | `plan.delta` | 计划文本增量，当前按观察型计划输出展示 |
| `turn/plan/updated` | `plan.updated` | 结构化计划步骤更新 |
| `item/commandExecution/outputDelta` | `tool.progress` | 命令执行输出 |
| `item/fileChange/outputDelta` | `tool.progress` | 文件修改类工具输出 |
| `item/mcpToolCall/progress` | `tool.progress` | MCP 工具输出 |
| `item/commandExecution/terminalInteraction` | `terminal.interaction` | terminal 交互信息，当前作为专门运行时事件展示 |
| `item/started` | `item.started` | item 生命周期开始，需按 `item.type` 继续分流 |
| `item/completed` | `item.completed` | item 生命周期结束，投影为 assistant/tool/plan 等完成态 |
| `thread/tokenUsage/updated` | `usage.updated` | token / context 使用量更新 |

### 系统事件

| method | 统一语义 | 作用 |
| --- | --- | --- |
| `thread/started` | `session.started` | 建立 native thread 绑定 |
| `turn/started` | `turn.started` | 建立 turn 生命周期 |
| `serverRequest/resolved` | `approval.resolved` | 审批 / 输入请求闭环 |
| `turn/completed` | `turn.terminal` | turn 收口 |
| `error` | `turn.error` | provider 失败收口 |
| `account/rateLimits/updated` | `account.rate_limits.updated` | 更新运行额度状态 |
| `thread/status/changed` | `thread.status.changed` | 更新 thread 状态 |
| `skills/changed` | `skills.changed` | 更新可用技能列表或版本 |
| `turn/diff/updated` | `thread.diff.updated` | 记录最新 diff / 增量同步标记 |

### 明确忽略

| method | 统一语义 | 原因 |
| --- | --- | --- |
| `item/reasoning/summaryPartAdded` | `reasoning.summary-part-added` | 只是 summary 分段元信息，不值得进入主路径 |
| `item/started` / `item/completed` 中的 `userMessage` | `user.message.echo` | 用户输入回声，不能二次渲染 |

### 仅观察或未知兜底

| 场景 | 当前策略 |
| --- | --- |
| 未注册 method | observe notice，完整保留 raw payload |
| 已注册 method 但 payload 不完整 | observe notice，完整保留 raw payload |
| 未识别 item type | observe notice，标题标明 unexpected item |

## 已验证的真实 external typed 事件

本机 `codex-cli 0.115.0` 样本已确认出现：

- `thread/started`
- `thread/status/changed`
- `turn/started`
- `item/started`
- `item/completed`
- `item/agentMessage/delta`
- `item/reasoning/summaryPartAdded`
- `item/reasoning/summaryTextDelta`
- `thread/tokenUsage/updated`
- `account/rateLimits/updated`
- `turn/completed`

样本同时确认：

- `item/started` / `item/completed` 会携带 `userMessage`，必须忽略。
- `item/started` / `item/completed` 当前实测 item type 主要是 `userMessage`、`reasoning`、`agentMessage`。
- 推理摘要流会经过 `item/reasoning/summaryPartAdded` 与 `item/reasoning/summaryTextDelta`，没有出现 unknown method。
- `thread/status/changed.params.status` 是结构化对象，不能按单一字符串假设。
- `account/rateLimits/updated` 的主要数据位于 `params.rateLimits`。
- `turn/start` 请求里的 sandbox 值应使用 `workspace-write`。

补充结论：

- 这轮额外做了“强制 shell / 强制文件修改”探针，但外部 app-server 实测仍没有产出 `item/commandExecution/outputDelta`、`item/fileChange/outputDelta`、`item/mcpToolCall/progress`、`turn/plan/updated`、`skills/changed`、`turn/diff/updated`。
- 同一轮里也没有出现任何未注册 method；当前 registry 对已观察到的外部 typed 通知覆盖完整。
- 但这不代表工具类 typed 事件不存在，只能说明在当前本机 `codex-cli 0.115.0`、当前模型和这些 prompt 下还没复现出来，后续仍需要更贴近真实任务的样本继续抓。

## 当前实现结论

目前 `openrelay` 已经完成下面几件事：

- adapter 正式输入面只剩 typed contract。
- legacy `codex/event/*` 外部兼容路径已删除。
- `app_server.py` 已退回到底层 transport / RPC 客户端职责。
- observe notice 已统一替代旧的 fallback 标记。
- typed system 事件已进入 runtime state，而不只是写入调试快照。

## 后续工作

这条主线剩下的工作不再是“兼容旧事件”，而是两类验证：

1. 用更多真实 `0.115.x` app-server 样本继续核对 schema，确认 registry 没漏项。
2. 根据真实样本，决定 `terminal.interaction`、`turn/diff/updated` 等事件是否要进一步提升展示或交互能力。
