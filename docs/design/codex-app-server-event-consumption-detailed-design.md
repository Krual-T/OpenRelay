# Codex App-Server 事件消费详细设计

更新时间：2026-03-17

## 设计定位

这份文档是在 [`docs/design/codex-app-server-event-consumption-plan.md`](/home/Shaokun.Tang/Projects/openrelay/docs/design/codex-app-server-event-consumption-plan.md) 的基础上，把后续实现需要落到的类、方法、状态边界和迁移顺序写清楚。

目标不是再叠一层 patch，而是在不改动 `agent_runtime -> runtime -> presentation` 主路径接口的前提下，对 `src/openrelay/backends/codex_adapter/` 做一次小范围结构重组，并把支持基线收敛到官方 `codex >= 0.115.0` 的 external typed app-server contract。

## 当前结构的问题

当前消费主路径已经是可工作的，但 `CodexProtocolMapper` 承担了过多职责：

- 原始 method 路由
- v1/v2 alias 去重
- turn/thread identity 提取
- 增量文本聚合
- item type 归类
- RuntimeEvent 生成
- fallback notice 生成
- terminal 判定

对应位置主要在 [`src/openrelay/backends/codex_adapter/mapper.py:150`](/home/Shaokun.Tang/Projects/openrelay/src/openrelay/backends/codex_adapter/mapper.py#L150) 到 [`src/openrelay/backends/codex_adapter/mapper.py:733`](/home/Shaokun.Tang/Projects/openrelay/src/openrelay/backends/codex_adapter/mapper.py#L733)。

这会带来三个问题：

1. 旧版本日志中的 external legacy `codex/event/*` 与当前 external contract 已经分叉，如果继续把它们当正式输入面，会让适配目标失真。
2. 当前去重主要还是围绕旧 alias 思路演进，而不是围绕稳定的 typed semantic key。
3. terminal 行为现在主要由 [`src/openrelay/backends/codex_adapter/turn_stream.py:67`](/home/Shaokun.Tang/Projects/openrelay/src/openrelay/backends/codex_adapter/turn_stream.py#L67) 开始的事件循环按 `event_type` 做收口，缺少“同一 turn 只能关闭一次”的显式模型。

## 约束

这次详细设计保持下面几个边界不动：

- `AgentRuntimeService` 对 backend 的调用方式不变，见 [`src/openrelay/agent_runtime/service.py:100`](/home/Shaokun.Tang/Projects/openrelay/src/openrelay/agent_runtime/service.py#L100)。
- `CodexSessionClient.start_turn()` 的对外职责不变，仍负责 thread 准备、stream 生命周期和 transport 订阅，见 [`src/openrelay/backends/codex_adapter/client.py:105`](/home/Shaokun.Tang/Projects/openrelay/src/openrelay/backends/codex_adapter/client.py#L105)。
- `LiveTurnReducer` 仍只消费稳定的 `RuntimeEvent`，不直接理解 provider method，见 [`src/openrelay/agent_runtime/reducer.py:33`](/home/Shaokun.Tang/Projects/openrelay/src/openrelay/agent_runtime/reducer.py#L33)。
- server request 审批闭环保留在 `CodexTurnStream`，不引入第二套交互入口，见 [`src/openrelay/backends/codex_adapter/turn_stream.py:95`](/home/Shaokun.Tang/Projects/openrelay/src/openrelay/backends/codex_adapter/turn_stream.py#L95)。

## 目标结构

目标链路收敛为：

```text
CodexTurnStream.handle_notification
  -> CodexProtocolMapper.map_notification
  -> CodexEventRegistry.lookup
  -> CodexSemanticMapper.map
  -> CodexSemanticDeduper.filter
  -> CodexRuntimeEventProjector.project
  -> RuntimeEventSink.publish
```

其中 `CodexProtocolMapper` 不再直接写所有 method 分支，而是退化成编排器和 facade。

## 推荐重构范围

### 保留的类

- `CodexRuntimeBackend`
- `CodexSessionClient`
- `CodexTurnStream`
- `CodexProtocolMapper`
- `CodexTurnState`

### 新增的类

- `CodexConsumptionMode`
- `CodexRawEventEnvelope`
- `CodexEventDescriptor`
- `CodexEventRegistry`
- `CodexSemanticEvent`
- `CodexSemanticMapper`
- `CodexSemanticDeduper`
- `CodexRuntimeEventProjector`
- `CodexTerminalState`

### 尽量不新增的东西

- 不新增第二套 reducer。
- 不把 typed/v1 分流逻辑上提到 `agent_runtime`。
- 不让 `LiveTurnReducer` 直接做语义去重。

## 类设计

### 1. `CodexConsumptionMode`

建议位置：

- `src/openrelay/backends/codex_adapter/event_registry.py`

建议定义：

```python
class CodexConsumptionMode(StrEnum):
    HYBRID = "hybrid"
    TYPED_ONLY = "typed-only"
```

职责：

- 明确 mapper 当前工作在哪个消费模式。
- `TYPED_ONLY` 默认开启，只消费 external typed contract。
- `HYBRID` 仅用于旧日志回放或低版本调试，不作为正式支持路径。

配置流向：

- `CodexRuntimeBackend.__init__`
- `CodexRuntimeBackend._get_client()`
- `CodexSessionClient.__init__`
- `CodexProtocolMapper.__init__`

这样 mode 是显式构造参数，不是埋在 method 分支里的隐式行为。

### 2. `CodexRawEventEnvelope`

建议位置：

- `src/openrelay/backends/codex_adapter/semantic_events.py`

建议字段：

- `method: str`
- `params: dict[str, Any]`
- `route: Literal["v1", "v2"]`
- `thread_id: str`
- `turn_id: str`
- `item_id: str`

职责：

- 把 identity 提取与 method 路由解耦。
- 原来 `_message_identity()`、`_item_id()` 的结果不再在多个分支重复提取。

主要方法：

- `CodexProtocolMapper._build_envelope(method, params) -> CodexRawEventEnvelope | None`

如果 thread/turn 不匹配当前 stream，直接在这里返回 `None`。

### 3. `CodexEventDescriptor`

建议位置：

- `src/openrelay/backends/codex_adapter/event_registry.py`

建议字段：

- `method: str`
- `route: Literal["v1", "v2"]`
- `semantic_name: str`
- `policy: Literal["render", "system", "ignore", "observe"]`
- `support_level: Literal["v1-only", "v2-only", "dual"]`
- `projector: str`
- `dedupe_scope: str`
- `terminal_kind: str`

职责：

- 作为事件注册表中的一行。
- “这个 raw method 是什么语义、应该走哪条 projector、要不要 dedupe、是不是 terminal”都由注册表声明，而不是散在 mapper 分支里。

这里把计划文档里的 `fallback` 命名收敛为 `observe`。

原因：

- `fallback` 更像实现细节。
- `observe` 更准确表达“收到、展示、保留原始 payload，但暂不纳入正式状态机”。

### 4. `CodexEventRegistry`

建议位置：

- `src/openrelay/backends/codex_adapter/event_registry.py`

主要职责：

- 维护 raw method -> descriptor 的静态注册表。
- 根据 `mode` 判断事件是否可进入当前消费链。
- 显式声明 ignore 集合，而不是靠“没分支所以没处理”。

建议主要方法：

- `lookup(method: str, mode: CodexConsumptionMode) -> CodexEventDescriptor | None`
- `is_enabled(descriptor: CodexEventDescriptor, mode: CodexConsumptionMode) -> bool`
- `is_terminal(descriptor: CodexEventDescriptor) -> bool`

这层不做状态聚合，也不生成 `RuntimeEvent`。

### 5. `CodexSemanticEvent`

建议位置：

- `src/openrelay/backends/codex_adapter/semantic_events.py`

建议字段：

- `semantic_name: str`
- `policy: Literal["render", "system", "ignore", "observe"]`
- `source_method: str`
- `source_route: Literal["v1", "v2"]`
- `thread_id: str`
- `turn_id: str`
- `item_id: str`
- `payload: dict[str, Any]`
- `dedupe_key: str`
- `terminal_kind: str`

职责：

- 代表已经脱离协议细节的内部语义事件。
- `payload` 只保留 projector 需要的稳定字段，不保留乱序的 provider 结构。

### 6. `CodexTerminalState`

建议位置：

- `src/openrelay/backends/codex_adapter/semantic_events.py`

建议字段：

- `closed: bool = False`
- `terminal_kind: str = ""`
- `source_route: str = ""`
- `source_method: str = ""`

加入到 `CodexTurnState`：

- `terminal: CodexTerminalState = field(default_factory=CodexTerminalState)`
- `seen_semantic_keys: set[str] = field(default_factory=set)`

职责：

- 把“一个 turn 只允许关闭一次”变成状态，而不是靠 `CodexTurnStream` 的 `done` 布尔值兜底。
- 允许记录“第一次成功收口来自 v1 还是 v2”，便于后续诊断。

### 7. `CodexSemanticMapper`

建议位置：

- `src/openrelay/backends/codex_adapter/semantic_mapper.py`

主要职责：

- 根据 descriptor 和 envelope，把 raw event 归一化为一个或多个 `CodexSemanticEvent`。
- 负责增量文本聚合、reasoning 合并、tool 输出拼装、usage 提取。

建议主要方法：

- `map(envelope, descriptor, state) -> tuple[CodexSemanticEvent, ...]`
- `_map_assistant_delta(...)`
- `_map_reasoning_delta(...)`
- `_map_plan_updated(...)`
- `_map_tool_started(...)`
- `_map_tool_progress(...)`
- `_map_tool_completed(...)`
- `_map_turn_terminal(...)`
- `_map_observe_event(...)`

### 7.1 按消息类型拆开的 mapper 责任

为了避免后续又回到“一个大分支里补特判”，`CodexSemanticMapper` 内部应该按消息职责分组，而不是按“哪里报过 bug”分组。

建议保持下面这组稳定边界：

| method / 语义 | 入口方法 | 主要职责 | 注意点 |
| --- | --- | --- | --- |
| `thread/started` / `session.started` | `_map_session_started()` | 提取 native session id/title，建立 thread 绑定语义。 | 不要混入 turn 初始化逻辑。 |
| `turn/started` / `turn.started` | `_map_turn_started()` | 标记 turn 生命周期开始。 | 只负责 turn 级 identity，不做 item 初始化。 |
| `item/agentMessage/delta` / `assistant.delta` | `_map_assistant_delta()` | 聚合 assistant 文本增量并投影为实时正文。 | 去重 key 必须包含 `item_id + delta`。 |
| `item/reasoning/textDelta`、`item/reasoning/summaryTextDelta` / `reasoning.delta` | `_map_reasoning()` | 按 content/summary 两条子通道聚合 reasoning 文本。 | 不能把 content 与 summary 混成一个索引空间。 |
| `item/plan/delta`、`turn/plan/updated` / `plan.delta`、`plan.updated` | `_map_plan()` | 处理非结构化计划增量与结构化计划列表。 | `item/plan/delta` 更接近展示流，不应伪装成结构化 plan step。 |
| `item/commandExecution/outputDelta`、`item/fileChange/outputDelta`、`item/mcpToolCall/progress` / `tool.progress` | `_map_tool_progress()` | 聚合工具过程输出。 | 不同工具类型要分开存储，避免 command/file-change 串流。 |
| `serverRequest/resolved` / `approval.resolved` | `_map_approval_resolved()` | 关闭 approval / server request 等待态。 | 只处理“已解决”，request 本身仍由 turn stream 闭环。 |
| `item/started` / `item.started` | `_map_item_started()` | 基于 `item.type` 决定这是 tool started、plan started、ignore 还是 observe。 | `userMessage` 必须直接忽略；未知 `item.type` 要完整 observe。 |
| `item/completed` / `item.completed` | `_map_item_completed()` | 基于 `item.type` 投影出 assistant completed、tool completed、plan updated 等。 | 同语义不能和 delta 路径重复消费；未知类型要完整 observe。 |
| `thread/tokenUsage/updated` / `usage.updated` | `_extract_usage()` + `usage.updated` 分支 | 提取 token/context usage 并更新状态。 | schema 不稳定时宁可不产出事件，也不要伪造 usage。 |
| `turn/completed`、`error` / terminal | `_map_terminal()` | 统一生成 turn completed / failed / interrupted 收口事件。 | 需要显式保证同一 turn 只关闭一次。 |
| `account/rateLimits/updated`、`thread/status/changed`、`skills/changed`、`turn/diff/updated` / 系统快照 | `_update_system_snapshot()` | 写入系统状态快照，供后续上层状态接入。 | 不要在这个方法里偷偷产出 render 事件。 |
| 未注册 method 或未知 item type | `_observe_event()` | 以 backend notice 形式展示完整 payload。 | 这是明确策略，不是异常兜底。 |

### 7.2 `item/started` / `item/completed` 的分流规则

`item/*` 是 typed contract 里最容易“同语义重复消费”的地方，因为它既是生命周期事件，又承载真实 item 数据。

建议明确分成 4 类：

| `item.type` | `item/started` | `item/completed` | 处理原则 |
| --- | --- | --- | --- |
| `userMessage` | ignore | ignore | 这是用户输入回声，不能驱动 UI 或状态机。 |
| `assistantMessage` | 通常不单独产出 render 事件 | 产出 assistant 完成态 | 增量正文主要来自 `item/agentMessage/delta`，完成态只在 completed 收口一次。 |
| `commandExecution`、`fileChange`、`mcpToolCall` | 产出 tool.started | 产出 tool.completed | 过程输出由各自的 `outputDelta/progress` 路径提供，开始与结束由 lifecycle 提供。 |
| `plan` | 可选择 observe 或 started 占位 | 产出 `plan.updated` | 避免和 `turn/plan/updated` 重复消费，需要以语义指纹去重。 |
| `reasoning` | 通常不单独展示 | 可根据 summary/content 聚合结果决定是否补完成态 | 不应重复追加已通过 delta 路径展示过的内容。 |
| 未知类型 | observe | observe | 完整展示原始 payload，便于后续分类。 |

这里的核心原则不是“尽量都接”，而是：

- 增量路径负责流式内容
- 生命周期路径负责开始/结束信号
- 同一语义只允许进入主状态机一次

### 7.3 系统消息后续要接到哪里

当前 `account/rateLimits/updated`、`thread/status/changed`、`skills/changed`、`turn/diff/updated` 只写入 `CodexTurnState.system_snapshot` 一类的内部状态，还没有真正进入上层可消费状态。

下一步实现时，建议分别接到下面这些职责位：

| 消息 | 建议接入点 | 作用 |
| --- | --- | --- |
| `thread/status/changed` | `CodexTurnStream` 所维护的 turn/thread 活跃状态，必要时透出到 runtime 查询面 | 让上层知道当前 thread 是 active 还是 idle。 |
| `account/rateLimits/updated` | runtime status 查询或面板数据源 | 让用户能看到限额而不是只存在底层快照。 |
| `skills/changed` | backend capability snapshot | 让后续技能面或诊断输出可读取最新能力列表。 |
| `turn/diff/updated` | transcript / history sync 入口 | 为后续真实历史同步留正式接点。 |

这里不要再用含糊词汇描述。实际含义就是：

- 现在这些消息“看到了”
- 但上层还“拿不到”
- 后续要把它们接到明确的状态出口上

这里承接当前 `mapper.py` 里以下方法的真实业务逻辑：

- `_map_agent_delta()`
- `_map_reasoning_content_delta()`
- `_map_reasoning_summary_delta()`
- `_map_plan_delta()`
- `_map_plan_updated()`
- `_map_tool_output_delta()`
- `_map_item_started()`
- `_map_item_completed()`
- `_map_token_usage_updated()`
- `_map_turn_completed()`

也就是把现有的“按 method 直接产 RuntimeEvent”，改成“按语义产 SemanticEvent”。

### 8. `CodexSemanticDeduper`

建议位置：

- `src/openrelay/backends/codex_adapter/event_deduper.py`

主要职责：

- 在 `HYBRID` 模式下按语义 key 去重。
- 实现 “v2 优先、v1 补位、terminal 只关闭一次”。

建议主要方法：

- `accept(event: CodexSemanticEvent, state: CodexTurnState) -> bool`
- `_accept_terminal(...) -> bool`
- `_accept_non_terminal(...) -> bool`
- `_source_priority(route: str) -> int`

核心规则：

1. 同一 `dedupe_key` 已出现过，则直接丢弃后到达的重复语义事件。
2. 如果先到的是 v1，后到的是等价 v2：
   - 非 terminal 直接丢掉后者或前者，取决于是否已经发布。
   - 推荐策略是“先到先发布，不做回滚替换”，否则链路会变复杂。
3. terminal 例外：
   - 第一个合法 terminal 负责收口。
   - 后续任何 terminal 不再改变 turn 状态。
   - 若后续 terminal 与已关闭 terminal 语义冲突，转成 `observe` 事件附加到 backend notice。

这里的关键是不要把“更偏好 v2”实现成“必须等 v2 再关 turn”。缺位时 v1 必须能单独收口。

### 9. `CodexRuntimeEventProjector`

建议位置：

- `src/openrelay/backends/codex_adapter/runtime_projector.py`

主要职责：

- 把 `CodexSemanticEvent` 投影为现有 `RuntimeEvent`。
- 保持 `LiveTurnReducer` 对 provider 协议无感知。

建议主要方法：

- `project(event: CodexSemanticEvent, state: CodexTurnState) -> tuple[RuntimeEvent, ...]`
- `_project_render_event(...)`
- `_project_system_event(...)`
- `_project_observe_event(...)`

建议投影规则：

- `assistant.delta` -> `AssistantDeltaEvent`
- `assistant.completed` -> `AssistantCompletedEvent`
- `reasoning.delta` -> `ReasoningDeltaEvent`
- `plan.updated` -> `PlanUpdatedEvent`
- `tool.started` -> `ToolStartedEvent`
- `tool.progress` -> `ToolProgressEvent`
- `tool.completed` -> `ToolCompletedEvent`
- `approval.requested` 保持现状，仍由 `map_server_request()` 直接产出
- `usage.updated` -> `UsageUpdatedEvent`
- `turn.completed` -> `TurnCompletedEvent`
- `turn.interrupted` -> `TurnInterruptedEvent`
- `turn.failed` -> `TurnFailedEvent`
- `observe` -> `BackendNoticeEvent`

对于 `thread.status.changed`、`skills.changed`、`turn.diff.updated`、`account.rate_limits.updated` 这种 system 事件，当前不建议立刻扩成新的 `agent_runtime` 公共事件类型。

更合适的做法是：

- 在 `CodexTurnState` 内部更新 system snapshot。
- 如果当前没有 runtime 主路径消费者，则不向 `LiveTurnReducer` 额外暴露。
- 如果后续需要展示或驱动上层状态，再单独把这些 system 语义提升成新的 `RuntimeEvent` 子类。

这样可以把本轮重构控制在 `codex_adapter` 内，而不是把半成熟语义扩散到整个 runtime 层。

## 对现有类的改造建议

### `CodexProtocolMapper`

保留现有公开方法：

- `build_thread_params()`
- `build_turn_start_params()`
- `map_notification()`
- `map_server_request()`
- `build_approval_response()`

但内部职责改为 facade：

- `map_notification()`
  - 调 `_build_envelope()`
  - 调 `registry.lookup()`
  - 调 `semantic_mapper.map()`
  - 调 `deduper.accept()`
  - 调 `runtime_projector.project()`

新增建议方法：

- `_build_envelope(method, params) -> CodexRawEventEnvelope | None`
- `_project_unknown_event(envelope) -> BackendNoticeEvent`

删除或内收的方法：

- `_duplicate_delta_alias()`
- 大部分 `_map_xxx()` method 分支

这些逻辑应迁到 `CodexSemanticMapper` 或 `CodexRuntimeEventProjector`。

### `CodexTurnState`

保留现有文本聚合缓存：

- `agent_text_by_id`
- `command_output_by_id`
- `file_change_output_by_id`
- `reasoning_by_id`
- `usage`
- `final_text`

新增：

- `seen_semantic_keys`
- `terminal`
- `system_snapshot`

其中 `system_snapshot` 可先用简单 dataclass：

- `thread_status: str`
- `last_diff_id: str`
- `skills_version: str`
- `rate_limits_payload: dict[str, Any]`

### `CodexTurnStream`

当前 `handle_notification()` 的主循环见 [`src/openrelay/backends/codex_adapter/turn_stream.py:67`](/home/Shaokun.Tang/Projects/openrelay/src/openrelay/backends/codex_adapter/turn_stream.py#L67)。

建议保留它作为“发布 RuntimeEvent 并驱动 future”的地方，但增强两个边界：

新增建议方法：

- `_publish_runtime_events(events: tuple[RuntimeEvent, ...]) -> None`
- `_consume_terminal_event(event: RuntimeEvent) -> BaseException | None`

设计原则：

- `mapper` 决定哪些 terminal 语义合法。
- `turn_stream` 只负责把合法 terminal 映射为 future 的 result 或 exception。

这样 terminal 规则的源头在 mapper 侧，而不是 stream 侧。

### `LiveTurnReducer`

当前 reducer 不需要大改。

只建议做一处轻量收敛：

- 现在 fallback 是通过 `BackendNoticeEvent` 的 `provider_payload["fallback"]` 识别，见 [`src/openrelay/agent_runtime/reducer.py:52`](/home/Shaokun.Tang/Projects/openrelay/src/openrelay/agent_runtime/reducer.py#L52)。
- 建议改成识别 `provider_payload["observe"]` 或 `provider_payload["classification"] == "observe"`。

原因：

- 和详细设计里的分类名保持一致。
- 避免 reducer 继续耦合 “fallback” 这种历史实现术语。

## 事件注册表的组织方式

建议不要把注册表写成运行时代码里的长串 `if`，而是声明成一个静态表。

建议字段：

| 列 | 含义 |
| --- | --- |
| `method` | 原始 app-server method |
| `route` | `v1` 或 `v2` |
| `semantic_name` | 统一语义名 |
| `policy` | `render/system/ignore/observe` |
| `projector` | 映射到哪类 projector |
| `dedupe_scope` | 哪些字段参与 dedupe |
| `support_level` | `v1-only/v2-only/dual` |
| `terminal_kind` | `completed/interrupted/failed/none` |
| `notes` | only-v1、补位、冲突说明 |

建议第一版先把下列事件显式登记：

- `thread/started`
- `turn/started`
- `item/agentMessage/delta`
- `codex/event/agent_message_content_delta`
- `codex/event/agent_message_delta`
- `item/reasoning/textDelta`
- `codex/event/reasoning_content_delta`
- `item/reasoning/summaryTextDelta`
- `codex/event/reasoning_summary_text_delta`
- `item/started`
- `codex/event/item_started`
- `item/completed`
- `codex/event/item_completed`
- `item/commandExecution/outputDelta`
- `codex/event/command_output_delta`
- `codex/event/exec_command_output_delta`
- `turn/plan/updated`
- `codex/event/plan_update`
- `thread/tokenUsage/updated`
- `codex/event/token_count`
- `turn/completed`
- `codex/event/task_complete`
- `codex/event/turn_aborted`
- `error`
- `account/rateLimits/updated`
- `thread/status/changed`
- `skills/changed`
- `turn/diff/updated`
- `codex/event/terminal_interaction`
- `item/commandExecution/terminalInteraction`

## terminal 规则

### 规则 1

只有下列语义允许关闭 turn：

- `turn.completed`
- `turn.interrupted`
- `turn.failed`

### 规则 2

`turn.completed`、`codex/event/task_complete`、`codex/event/turn_aborted`、`error(willRetry != true)` 都必须先归一到 terminal semantic，再由 deduper 决定是否接收。

### 规则 3

第一个接收成功的 terminal semantic 负责：

- 更新 `CodexTurnState.terminal`
- 发布对应 `RuntimeEvent`
- 让 `CodexTurnStream.future` 收口

### 规则 4

后到达的重复 terminal：

- 同 terminal kind：ignore
- 不同 terminal kind：observe

这样不会出现“先 completed 又被 aborted 覆盖”的状态倒退。

## only-v1 / dual / only-v2 的处理原则

### only-v1

必须进入注册表，并在 `HYBRID` 下可消费。

第一优先级包括：

- `codex/event/turn_aborted`
- `codex/event/plan_update`
- `codex/event/exec_command_output_delta`
- `codex/event/terminal_interaction`

### dual

必须共用同一个 `semantic_name` 和 dedupe 规则。

第一优先级包括：

- assistant delta
- reasoning delta
- item started/completed
- token usage
- turn completed / task_complete

### only-v2

先显式登记为 system 或 ignore，不接受“未来再说”的隐式未处理。

第一优先级包括：

- `account/rateLimits/updated`
- `thread/status/changed`
- `skills/changed`
- `turn/diff/updated`

## 迁移顺序

### 第一步

先引入注册表和 `CodexConsumptionMode`，但行为保持与现在一致。

关闭条件：

- 现有 `map_notification()` 仍能覆盖全部已知 method。
- 未知事件仍会走 observe notice。

### 第二步

把 `_map_xxx()` 逻辑从 `CodexProtocolMapper` 拆到 `CodexSemanticMapper` 和 `CodexRuntimeEventProjector`。

关闭条件：

- `CodexProtocolMapper` 只保留 facade 和审批映射。
- 绝大多数 method 分支从 mapper 主类移出。

### 第三步

引入 `CodexSemanticDeduper` 和 `CodexTerminalState`，替换当前 alias 级去重。

关闭条件：

- dual-route assistant delta 不重复渲染。
- dual-route tool output 不重复渲染。
- v1 terminal 缺位补位能正常收口。
- terminal 冲突不会二次关闭 turn。

### 第四步

补 system snapshot，但不急着提升为新的 runtime 公共事件。

关闭条件：

- `thread/status/changed`
- `skills/changed`
- `turn/diff/updated`
- `account/rateLimits/updated`

这些事件都已有明确注册和内部消费去向。

## 需要特别避免的坏设计

### 坏设计 1

在 `map_notification()` 里继续加更多 `if method in {...}`，只是把 if 搬大，没有改变结构。

### 坏设计 2

让 `LiveTurnReducer` 负责 dedupe。

这会把 provider-specific 问题泄漏到 runtime 公共层。

### 坏设计 3

为了兼容 v1，再加一套独立 `legacy mapper`。

这样会让双轨长期并存，进一步加重重复消费问题。

### 坏设计 4

把所有未知事件都当 ignore。

这正是飞书卡死和诊断困难的来源之一。

## 最小实现边界

如果后续按这份设计落地，第一批应该只碰下面这些文件：

- [`src/openrelay/backends/codex_adapter/mapper.py`](/home/Shaokun.Tang/Projects/openrelay/src/openrelay/backends/codex_adapter/mapper.py)
- [`src/openrelay/backends/codex_adapter/turn_stream.py`](/home/Shaokun.Tang/Projects/openrelay/src/openrelay/backends/codex_adapter/turn_stream.py)
- [`src/openrelay/backends/codex_adapter/client.py`](/home/Shaokun.Tang/Projects/openrelay/src/openrelay/backends/codex_adapter/client.py)
- `src/openrelay/backends/codex_adapter/event_registry.py`
- `src/openrelay/backends/codex_adapter/semantic_events.py`
- `src/openrelay/backends/codex_adapter/semantic_mapper.py`
- `src/openrelay/backends/codex_adapter/event_deduper.py`
- `src/openrelay/backends/codex_adapter/runtime_projector.py`

`agent_runtime` 层最多只做术语统一级的小改动，不应该成为这轮重构的主战场。

## 结论

这次重构的核心不是“再补几个 method 分支”，而是把当前 `CodexProtocolMapper` 中混杂的四件事拆开：

- raw method 注册
- semantic 归一化
- semantic 去重
- runtime 投影

只要这四层拆开，`HYBRID` 默认、`TYPED_ONLY` 实验、v1 only 补位、unknown observe 和 terminal 单次收口就能同时成立，而且改动范围仍然能控制在 `codex_adapter` 内。
