# Codex App-Server 双轨事件消费设计

更新时间：2026-03-17

## 这份设计要解决什么问题

`codex app-server` 当前还处在迁移期。

对 `openrelay` 来说，问题不是“要不要消费 app-server”，而是：

1. 同一个语义事件可能同时从 v2 typed 路线和 v1 legacy 路线发出来。
2. 有些事件只有 v2 有，有些事件只有 v1 有，有些两边都有但字段不完全对齐。
3. 如果直接按原始 method 分支消费，就很容易出现重复渲染、状态机漏推进、终态丢失和调试困难。
4. 目前飞书卡死的风险点已经不只是“未知事件没展示出来”，而是“终态或关键系统事件漏消费导致 turn 无法收口”。

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

### 3. 双轨可并存，但不能双消费

迁移期允许同时接 v1 和 v2。

但运行时状态推进必须围绕“语义事件”去重，而不是围绕“原始 method”去重。

### 4. 终态优先保证

会影响 turn/session 收口的事件优先级最高。

即使仍处于 hybrid 阶段，也必须保证：

- turn 能开始
- turn 能结束
- approval 能闭环
- 工具生命周期能收口

## 设计结论

当前阶段不应该把 `openrelay` 切到 `v2-only`。

建议引入显式消费模式：

- `hybrid`
  - 默认值
  - 同时接收 v2 和 v1
  - 按语义去重
- `typed-only`
  - 实验模式
  - 只接 v2 typed 事件
  - 允许用于迁移验证，不作为默认

不建议引入长期存在的 `legacy-only`。

`legacy-only` 可以只作为调试开关存在，不进入正式主配置面。

## 事件分层模型

原始事件进入 adapter 后，先转换成内部语义层：

```text
RawEvent(v1/v2)
  -> SemanticEvent
  -> ConsumptionPolicy(render | system | ignore | fallback)
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

### 1. 当前更像 v1 only 的事件

这些事件在本地日志中已观察到，且目前没有稳定对应的 v2 主路径证据，必须在 hybrid 模式继续支持。

| 原始事件 | 语义事件 | 消费类型 | 说明 |
| --- | --- | --- | --- |
| `codex/event/turn_aborted` | `turn.interrupted` 或 `turn.failed` | 系统 | 高优先级；终态事件，漏掉会导致 turn 卡住 |
| `codex/event/plan_update` | `plan.updated` | 渲染 | 作为 `turn/plan/updated` 缺失时的 legacy 补位 |
| `codex/event/exec_command_output_delta` | `tool.progress` | 渲染 | 作为 command output 的 legacy 补位 |
| `codex/event/terminal_interaction` | `terminal.interaction` | 兜底 | 暂不进入正式交互模型 |
| `codex/event/agent_reasoning` | `reasoning.delta` 或 `reasoning.completed` | 渲染 | 需要确认是否和 item completed 重复 |
| `codex/event/agent_reasoning_section_break` | `reasoning.section.break` | ignore | 当前无明确 UI 价值 |

### 2. 当前更像 v2 only 的事件

这些事件更接近公共 app-server typed surface，建议优先按 v2 语义消费。

| 原始事件 | 语义事件 | 消费类型 | 说明 |
| --- | --- | --- | --- |
| `account/rateLimits/updated` | `account.rate_limits.updated` | 系统 | 面板与状态查询需要 |
| `thread/status/changed` | `thread.status.changed` | 系统 | session / panel 状态刷新 |
| `skills/changed` | `skills.changed` | 系统 | provider 能力变化 |
| `turn/diff/updated` | `thread.diff.updated` | 系统 | 用于线程历史增量同步 |

### 3. 当前双轨都有的事件

这类事件必须定义同语义归并规则，禁止原始 method 各自单独推进状态。

| v2 | v1 | 统一语义 | 消费类型 |
| --- | --- | --- | --- |
| `thread/started` | 无稳定 legacy 主路径证据 | `session.started` | 系统 |
| `turn/started` | `codex/event/task_started` | `turn.started` | 系统 |
| `item/agentMessage/delta` | `codex/event/agent_message_content_delta` / `codex/event/agent_message_delta` | `assistant.delta` | 渲染 |
| `item/reasoning/textDelta` | `codex/event/reasoning_content_delta` | `reasoning.delta` | 渲染 |
| `item/reasoning/summaryTextDelta` | `codex/event/reasoning_summary_text_delta` | `reasoning.delta` | 渲染 |
| `item/commandExecution/outputDelta` | `codex/event/command_output_delta` | `tool.progress` | 渲染 |
| `item/started` | `codex/event/item_started` | `tool.started` | 渲染 |
| `item/completed` | `codex/event/item_completed` | `assistant.completed` / `tool.completed` / `reasoning.delta` | 渲染 |
| `thread/tokenUsage/updated` | `codex/event/token_count` | `usage.updated` | 渲染 |
| `turn/completed` | `codex/event/task_complete` | `turn.completed` / `turn.interrupted` / `turn.failed` | 系统 |

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

同一语义双轨同时到达时，建议优先级如下：

1. `v2 typed`
2. `v1 legacy`

但有一个例外：

- 终态事件如果 v2 没来，v1 terminal event 必须独立收口，不能因为“更偏好 v2”而放弃。

也就是说，优先级只影响“冲突时谁赢”，不影响“缺位时谁补位”。

## 终态事件的特殊规则

终态是最危险的一类。

建议定义单独规则：

### 1. terminal semantics

terminal 只允许以下三种：

- `turn.completed`
- `turn.interrupted`
- `turn.failed`

### 2. terminal sources

这些原始事件都可以触发 terminal：

- `turn/completed`
- `codex/event/task_complete`
- `codex/event/turn_aborted`
- `error` 且 `willRetry != true`

### 3. terminal resolution

优先按下面顺序解释：

1. `turn/completed.turn.status`
2. `codex/event/turn_aborted.reason`
3. `error`
4. `codex/event/task_complete.msg`

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

当前建议明确 ignore 的事件：

- `codex/event/raw_response_item`
- `codex/event/user_message`
- `codex/event/web_search_begin`
- `codex/event/web_search_end`
- `codex/event/exec_command_begin`
- `codex/event/exec_command_end`
- `codex/event/mcp_startup_complete`
- `codex/event/skills_update_available`
- `codex/event/agent_reasoning_section_break`

其中 `web_search_begin/end`、`exec_command_begin/end` 之所以建议 ignore，是因为如果 `item/started` / `item/completed` 已存在，再让 begin/end 也推进工具状态，只会制造重复生命周期。

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

- `CODEX_APP_SERVER_EVENT_MODE=hybrid|typed-only`

默认值：

- `hybrid`

原因：

- 当前官方和本地日志都表明双轨仍在
- 终态和关键推进事件并未完全收口到 typed v2
- 直接默认 `typed-only` 风险过高

建议暂时不要把它做成用户侧复杂矩阵配置。

消费模式只决定“接不接 legacy 路”，不决定 UI 行为。

UI 行为由事件分类表决定。

## 推荐实施顺序

### Phase 1：先把分类表和去重层立起来

- 引入 `SemanticEvent`
- 引入 `ConsumptionPolicy`
- 引入 `SemanticEventKey`
- 把现有 mapper 分支改成“原始事件 -> 语义事件 -> runtime event”

### Phase 2：先补 terminal 与 tool legacy 漏洞

优先补：

- `codex/event/turn_aborted`
- `codex/event/plan_update`
- `codex/event/exec_command_output_delta`
- `codex/event/terminal_interaction`

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

这轮设计最关键的不是“要不要全面拥抱 v2”，而是：

- 在迁移未完成前，`openrelay` 必须先成为一个稳定的 hybrid consumer
- hybrid 不代表双写双吃
- hybrid 的正确实现方式是“单一语义层 + 去重 + 分类表”

只有这样，后续才能安全地逐步收紧到 `typed-only`。
