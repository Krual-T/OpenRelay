# Codex App-Server Typed Contract 适配设计

更新时间：2026-03-17

## 这份设计要解决什么问题

从官方 `codex 0.115.0` 开始，external app-server transport（`stdio` / `websocket`）已经不再发 `codex/event/*` legacy 通知。

对 `openrelay` 来说，当前问题已经不该继续定义成“v1/v2 双轨如何长期并存”，而应该定义成：

1. `openrelay` 走的是 external `codex app-server` 子进程协议，不是官方 TUI/exec 使用的 in-process internal app-server。
2. 因此支持基线应该直接收敛到 `codex >= 0.115.0` 的 typed contract，而不是继续把 external legacy 通知当正式输入面。
3. 即使不再消费 external legacy，仍然需要稳定的语义层、terminal 收口和 unknown event observe。
4. 目前的高风险点变成“typed schema 是否覆盖完整”，而不是“only-v1 事件是否漏接”。

这份设计的目标是把事件消费路径收敛成一套明确策略：

- 哪些事件属于同一语义
- 哪些事件必须消费
- 哪些事件只用于系统状态推进
- 哪些事件明确忽略
- 双轨同时到达时如何避免二次消费

## 设计目标

### 1. 语义先于协议

`openrelay` 不直接围绕 `item/...` 或 `codex/event/...` 写主路径逻辑。

所有原始事件都要先归一化成更稳定的“语义事件”。

### 2. 覆盖全部观察到的事件

不接受“未知事件直接静默丢掉”。

对于每个观察到的事件，必须落入下面三类之一：

- 渲染消费
- 系统消费
- 明确忽略

如果当前还没决定，就先落到“兜底展示 + 待分类”，而不是隐式无视。

### 3. typed contract 优先

运行时默认只以 typed app-server notification / server request 为正式输入面。

`codex/event/*` 在 external transport 上只作为调试期观测对象，不再是主路径兼容目标。

### 4. 终态优先保证

会影响 turn/session 收口的事件优先级最高。

即使仍处于 hybrid 阶段，也必须保证：

- turn 能开始
- turn 能结束
- approval 能闭环
- 工具生命周期能收口

## 设计结论

当前阶段应该把 `openrelay` 的正式支持基线收敛到：

- `codex >= 0.115.0`
- external `codex app-server` typed contract

建议消费模式改为：

- `typed-only`
  - 默认值
  - 只接 typed app-server 事件
  - 作为正式支持路径
- `hybrid`
  - 仅调试模式
  - 只用于回放旧日志或排查低版本 Codex
  - 不再作为默认，也不作为长期产品目标

不建议继续扩展 `legacy-only` 或 external legacy 兼容矩阵。

## 事件分层模型

原始事件进入 adapter 后，先转换成内部语义层：

```text
RawEvent(typed)
  -> SemanticEvent
  -> ConsumptionPolicy(render | system | ignore | observe)
  -> RuntimeEvent / session mutation / debug notice
```

其中：

- `RawEvent`：原始 method + params
- `SemanticEvent`：稳定语义名
- `ConsumptionPolicy`：定义这类事件的处理策略

## 语义事件分类

### A. 必须渲染消费的事件

这类事件要进入 live turn 视图，用户可感知。

| 语义事件 | 作用 |
| --- | --- |
| `assistant.delta` | 流式正文增量 |
| `assistant.completed` | assistant item 终态文本 |
| `reasoning.delta` | 推理或摘要增量 |
| `plan.delta` | 非结构化计划增量 |
| `plan.updated` | 结构化计划更新 |
| `tool.started` | 工具开始 |
| `tool.progress` | 工具增量输出 |
| `tool.completed` | 工具结束 |
| `approval.requested` | 审批 / 用户输入请求 |
| `approval.resolved` | 审批闭环确认 |
| `usage.updated` | token / context 使用量 |

### B. 必须系统消费的事件

这类事件不一定直接渲染，但必须推进状态机。

| 语义事件 | 作用 |
| --- | --- |
| `session.started` | 建立 native thread binding |
| `turn.started` | 建立 turn 生命周期 |
| `turn.completed` | 正常收口 turn |
| `turn.interrupted` | 中断收口 turn |
| `turn.failed` | 失败收口 turn |
| `thread.status.changed` | 更新 thread 状态与 panel / resume 视图 |
| `thread.diff.updated` | 后续 transcript / session timeline 增量同步入口 |
| `skills.changed` | 运行时能力面刷新入口 |
| `account.rate_limits.updated` | 面板 / 状态查询的 provider 运行额度 |

### C. 明确忽略的事件

这类事件要么是重复回声，要么是 provider 内部中间态，不应该进入主状态机。

| 语义事件 | 忽略理由 |
| --- | --- |
| `raw.response.item` | 原始响应碎片，语义层太低，容易和 item 完成态重复 |
| `user.message.echo` | 用户输入已在上游掌握，不需要由 backend 回推再驱动 UI |
| `task.started.legacy` | 如果 `turn.started` 或 `item.started` 已存在，则只属兼容噪音 |
| `skills.update.available` | 更像 provider 通知，不是当前 turn 状态 |
| `mcp.startup.complete` | provider 内部准备态，不影响当前 turn 展示 |
| `reasoning.section.break` | 若没有独立 UI 语义，直接忽略比半消费更稳定 |

### D. 未决但必须兜底展示的事件

这类事件当前还没决定是否进入长期模型，但不能静默。

| 语义事件 | 临时策略 |
| --- | --- |
| `terminal.interaction` | 先作为 backend notice 展示完整 payload |
| 未识别 item type 的 started/completed | backend notice + raw payload |
| 未识别 method | backend notice + raw payload |

## 事件覆盖矩阵

下面这张表按“v1 only / v2 only / 双轨都有”来划分当前已知事件。

### 1. external contract 不再作为正式输入面的 legacy 事件

这些事件来自旧日志或官方 internal/in-process 迁移路径，不再作为 `openrelay` external app-server 适配的正式输入面。

| 原始事件 | 语义事件 | 消费类型 | 说明 |
| --- | --- | --- | --- |
| `codex/event/turn_aborted` | `turn.interrupted` 或 `turn.failed` | observe | external `0.115.0` 后不应再依赖 |
| `codex/event/plan_update` | `plan.updated` | observe | 旧日志回放时可观测，不作正式适配目标 |
| `codex/event/exec_command_output_delta` | `tool.progress` | observe | 同上 |
| `codex/event/terminal_interaction` | `terminal.interaction` | observe | 同上 |
| `codex/event/agent_reasoning` | `reasoning.delta` 或 `reasoning.completed` | observe | 同上 |
| `codex/event/agent_reasoning_section_break` | `reasoning.section.break` | ignore | 同上 |

### 2. 当前更像 v2 only 的事件

这些事件更接近公共 app-server typed surface，建议优先按 v2 语义消费。

| 原始事件 | 语义事件 | 消费类型 | 说明 |
| --- | --- | --- | --- |
| `account/rateLimits/updated` | `account.rate_limits.updated` | 系统 | 面板与状态查询需要 |
| `thread/status/changed` | `thread.status.changed` | 系统 | session / panel 状态刷新 |
| `skills/changed` | `skills.changed` | 系统 | provider 能力变化 |
| `turn/diff/updated` | `thread.diff.updated` | 系统 | 用于线程历史增量同步 |

### 2.1 已用本机 `codex-cli 0.115.0` 验证到的真实 external typed 事件

在一次真实 `initialize -> thread/start -> turn/start` 样本里，实际收到的通知方法包括：

- `thread/status/changed`
- `turn/started`
- `item/started`
- `item/completed`
- `item/agentMessage/delta`
- `thread/tokenUsage/updated`
- `account/rateLimits/updated`
- `turn/completed`

同一轮样本还确认了 3 个实现细节：

- `item/started` / `item/completed` 会出现 `userMessage` item，不应被当成 unexpected item notice。
- `thread/status/changed.params.status` 是结构化对象，如 `{type: "active"}`，不能直接按普通字符串假设。
- `account/rateLimits/updated` 的主要数据位于 `params.rateLimits` 下，而不是平铺在根层。

### 3. 旧日志与新协议存在重名语义，但正式实现按 typed-only 收敛

这类事件曾经存在双轨，但对 `codex >= 0.115.0` external transport 来说，正式实现应只消费 typed 路线。

| v2 | v1 | 统一语义 | 消费类型 |
| --- | --- | --- | --- |
| `thread/started` | 无稳定 legacy 主路径证据 | `session.started` | 系统 |
| `turn/started` | `codex/event/task_started` | `turn.started` | typed-only 正式消费 |
| `item/agentMessage/delta` | `codex/event/agent_message_content_delta` / `codex/event/agent_message_delta` | `assistant.delta` | typed-only 正式消费 |
| `item/reasoning/textDelta` | `codex/event/reasoning_content_delta` | `reasoning.delta` | typed-only 正式消费 |
| `item/reasoning/summaryTextDelta` | `codex/event/reasoning_summary_text_delta` | `reasoning.delta` | typed-only 正式消费 |
| `item/commandExecution/outputDelta` | `codex/event/command_output_delta` | `tool.progress` | typed-only 正式消费 |
| `item/started` | `codex/event/item_started` | `tool.started` | typed-only 正式消费 |
| `item/completed` | `codex/event/item_completed` | `assistant.completed` / `tool.completed` / `reasoning.delta` | typed-only 正式消费 |
| `thread/tokenUsage/updated` | `codex/event/token_count` | `usage.updated` | typed-only 正式消费 |
| `turn/completed` | `codex/event/task_complete` | `turn.completed` / `turn.interrupted` / `turn.failed` | typed-only 正式消费 |

## 去重不是按 method，而是按语义指纹

### 原则

`hybrid` 模式下，adapter 先产出 `SemanticEventKey`，再按 key 去重。

不允许：

- `item/agentMessage/delta` 进一次
- `codex/event/agent_message_content_delta` 再进一次

### 语义指纹建议

| 语义事件 | 去重 key |
| --- | --- |
| `assistant.delta` | `thread_id + turn_id + item_id + normalized_delta` |
| `reasoning.delta` | `thread_id + turn_id + item_id + channel(content/summary) + index + normalized_delta` |
| `tool.progress` | `thread_id + turn_id + item_id + output_kind + normalized_delta` |
| `tool.started` | `thread_id + turn_id + item_id + semantic_status(started)` |
| `tool.completed` | `thread_id + turn_id + item_id + semantic_status(completed)` |
| `plan.updated` | `thread_id + turn_id + stable_plan_hash` |
| `usage.updated` | `thread_id + turn_id + usage_hash` |
| `turn.completed` / `turn.interrupted` / `turn.failed` | `thread_id + turn_id + terminal_kind` |

### 去重优先级

正式运行时不再依赖 external 双轨并存。

默认只消费 typed 路线；legacy 事件即使偶然出现，也只进入 observe/debug，不参与主状态推进。

## 终态事件的特殊规则

终态是最危险的一类。

建议定义单独规则：

### 1. terminal semantics

terminal 只允许以下三种：

- `turn.completed`
- `turn.interrupted`
- `turn.failed`

### 2. terminal sources

这些 typed 原始事件可以触发 terminal：

- `turn/completed`
- `error` 且 `willRetry != true`

### 3. terminal resolution

优先按下面顺序解释：

1. `turn/completed.turn.status`
2. `error`

### 4. single-close rule

一个 turn 只允许第一次 terminal 事件真正关闭 future。

后续再来的 terminal 只记录 debug notice，不再二次推进状态。

## item 事件的消费策略

不是所有 item 都应该进主展示。

### 要进入主展示的 item

| item.type | 语义 | 策略 |
| --- | --- | --- |
| `agentMessage` | assistant 文本 | 渲染 |
| `reasoning` | reasoning 文本 | 渲染 |
| `plan` | plan | 渲染 |
| `commandExecution` | command tool | 渲染 |
| `fileChange` | file change tool | 渲染 |
| `webSearch` | web search tool | 渲染 |
| `mcpToolCall` | mcp tool | 渲染 |
| `collabAgentToolCall` | custom tool | 渲染 |

### 不进入主展示的 item

| item.type | 策略 |
| --- | --- |
| 未识别类型 | backend notice 兜底，不直接进入 tools 主列表 |

## 系统事件的消费策略

系统事件不一定要用户实时看到，但必须有稳定归宿。

| 语义事件 | 当前用途 | 建议归宿 |
| --- | --- | --- |
| `session.started` | 写回 native session id | binding store |
| `turn.started` | 建立 running turn | runtime turn stream |
| `turn.completed` / `turn.interrupted` / `turn.failed` | resolve future / close stream | runtime turn stream |
| `thread.status.changed` | thread 状态刷新 | session store / panel view model |
| `thread.diff.updated` | transcript 增量同步 | session history pipeline |
| `skills.changed` | provider 能力缓存失效 | backend capability cache |
| `account.rate_limits.updated` | provider 运行额度刷新 | runtime status / panel |

## 明确 ignore 的规则

ignore 不是“没看见”，而是“看见了并确认不该驱动主路径”。

建议所有 ignore 事件都：

- 保留 debug log
- 不进入 runtime event
- 不进入 live turn state
- 不参与 terminal 判定

当前阶段 external typed contract 下，ignore 集合应优先围绕 typed 内部中间态和明确无 UI 价值的事件来建，而不是继续扩展 legacy ignore 列表。

## fallback 规则

任何未命中的原始事件，都不能直接静默丢弃。

统一落到：

- `backend.notice`
- `provider_payload.fallback = true`
- 附完整 `raw_event`

这条规则的作用不是把 fallback 当长期主路径，而是：

- 先让支持人员看见事件内容
- 再决定它未来属于 render / system / ignore 哪一类

## 配置建议

建议新增一个明确配置项：

- `CODEX_APP_SERVER_EVENT_MODE=typed-only|hybrid`

默认值：

- `typed-only`

原因：

- 官方 `0.115.0` external transport 已停止发 `codex/event/*`
- `openrelay` 当前走的是 external app-server 子进程协议
- 继续把 external legacy 当默认输入面只会让目标 contract 模糊

建议暂时不要把它做成用户侧复杂矩阵配置。

`hybrid` 只用于旧日志回放或排查低版本兼容问题，不作为正式产品默认。

消费模式只决定“是否保留 legacy 观测面”，不决定 UI 行为。

UI 行为由事件分类表决定。

## 推荐实施顺序

### Phase 1：先把分类表和去重层立起来

- 引入 `SemanticEvent`
- 引入 `ConsumptionPolicy`
- 引入 `SemanticEventKey`
- 把现有 mapper 分支改成“原始事件 -> 语义事件 -> runtime event”

### Phase 2：用真实 `0.115.x` schema 校正 typed 事件表

优先确认：

- `turn/completed`
- `item/*`
- `thread/tokenUsage/updated`
- `serverRequest/*`

### Phase 3：补系统级 typed-only 事件

补：

- `account/rateLimits/updated`
- `thread/status/changed`
- `skills/changed`
- `turn/diff/updated`

### Phase 4：把 ignore 集合显式化

不是“没写分支”，而是显式注册：

- ignore 事件名
- ignore 原因
- 是否保留 debug log

## 本设计的硬约束

实现时必须满足下面 6 条：

1. 不能再按原始 method 直接推进 live turn 主状态。
2. 同一语义事件不能因双轨同时到达而重复渲染。
3. terminal event 必须只收口一次，但不能漏收口。
4. 每个已观察到的事件都必须有明确归类。
5. ignore 必须显式，不允许靠“没有分支”实现忽略。
6. fallback 必须保留完整原始 payload，方便后续支持和分类。

## 当前最重要的判断

这轮设计最关键的不是“还要不要继续兼容 external legacy”，而是：

- `openrelay` 必须直接以 `codex >= 0.115.0` external typed contract 为支持基线
- typed-only 不等于按 method 生写分支，仍然需要单一语义层 + 去重 + 分类表
- legacy 路径只保留 observe/debug 价值，不再进入正式状态机
