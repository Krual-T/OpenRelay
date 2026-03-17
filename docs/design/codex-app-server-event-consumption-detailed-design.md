# Codex App-Server 事件消费详细设计

更新时间：2026-03-17

## 设计定位

这份文档只描述当前 typed-only 实现的结构、边界和后续小范围演进点。

前提已经固定：

- `openrelay` 只对接 external `codex app-server`
- 支持基线是 `codex >= 0.115.0`
- 主路径只消费 typed contract
- 不再保留 external legacy `codex/event/*` 双轨兼容

所以这里不再讨论 `v1 / v2` 取舍，也不再讨论 `hybrid` 模式，而是直接说明现有体系下各个类应该负责什么。

## 现有结构

### 1. app-server transport 层

文件：`src/openrelay/backends/codex_adapter/app_server.py`

核心类：`CodexAppServerClient`

职责：

- 启动和关闭 `codex app-server` 子进程
- 维护 JSON-RPC 请求 / 响应
- 处理 transport 层 notification 分发
- 处理 server request 的默认响应
- 提供 `list_threads()`、`read_thread()`、`compact_thread()` 等辅助 RPC

明确不再负责：

- 旧版 turn 事件流消费
- 旧版 thread/turn 生命周期拼装
- external legacy 事件兼容

### 2. 单轮流式消费层

文件：`src/openrelay/backends/codex_adapter/turn_stream.py`

核心类：`CodexTurnStream`

关键方法：

- `stream()`：消费这一轮 turn 的 typed 事件并产出统一 `RuntimeEvent`
- `_handle_notification()`：处理 typed notification
- `_handle_server_request()`：处理审批、输入请求等 server request 闭环

职责：

- 订阅当前 turn 相关消息
- 调用 mapper 把 raw notification 变成统一运行时事件
- 在 turn terminal 时结束流
- 保持 approval / input request 交互闭环

### 3. 协议映射入口

文件：`src/openrelay/backends/codex_adapter/mapper.py`

核心类：`CodexProtocolMapper`

关键方法：

- `map_notification()`：typed notification 主入口
- `_build_envelope()`：提取 thread_id / turn_id / item_id 等稳定 identity
- `_observe_unknown_event()`：为未识别消息生成 observe notice

职责：

- 把 transport 收到的 method + params 组织成统一 envelope
- 从 registry 查 descriptor
- 调 semantic mapper 生成语义事件
- 调 runtime projector 投影为 `RuntimeEvent`

注意点：

- `CodexProtocolMapper` 现在是编排器，不再维护一套 legacy alias 分支表。
- 未注册 method 不会被静默丢弃，而是直接变成 observe notice。

### 4. 静态事件注册表

文件：`src/openrelay/backends/codex_adapter/event_registry.py`

核心结构：

- `CodexEventDescriptor`
- `CodexEventRegistry`

每一条注册项声明：

- 原始 `method`
- route（当前固定为 `v2`）
- 统一语义名
- policy：`render | system | ignore`
- projector / dedupe / terminal 等辅助元数据

职责：

- 让“这条 typed method 应该怎么处理”集中声明
- 避免 method 分支分散在多个文件里

### 5. 语义映射层

文件：`src/openrelay/backends/codex_adapter/semantic_mapper.py`

核心类：`CodexSemanticMapper`

关键方法：

- `map()`
- `_map_session_started()`
- `_map_turn_started()`
- `_map_assistant_delta()`
- `_map_reasoning()`
- `_map_plan()`
- `_map_tool_progress()`
- `_map_terminal_interaction()`
- `_map_approval_resolved()`
- `_map_item_started()`
- `_map_item_completed()`
- `_map_terminal()`
- `_map_system_event()`
- `_observe_event()`

职责：

- 把 raw typed payload 收敛成稳定语义事件
- 聚合 assistant / reasoning / tool 等流式文本
- 把 `item/started`、`item/completed` 继续按 `item.type` 分流
- 对无法稳定归类的消息生成 observe notice

当前特别规则：

- `userMessage` item 明确忽略，不再进入主展示。
- `terminal.interaction` 已有独立语义，不走“未知事件兜底”。
- `thread/status/changed`、`skills/changed`、`turn/diff/updated` 已作为 system 事件进入正式映射。

### 6. 运行时投影层

文件：`src/openrelay/backends/codex_adapter/runtime_projector.py`

核心类：`CodexRuntimeEventProjector`

职责：

- 把 `CodexSemanticEvent` 投影成 backend-neutral `RuntimeEvent`
- 让上层 reducer 只处理统一运行时语义

这里是 provider contract 和 `agent_runtime` 之间的最后一道边界。

### 7. 运行时状态层

文件：`src/openrelay/agent_runtime/reducer.py`

核心类：`LiveTurnReducer`

当前已消费的 typed system 事件：

- `SessionStartedEvent`
- `ThreadStatusUpdatedEvent`
- `RateLimitsUpdatedEvent`
- `SkillsUpdatedEvent`
- `ThreadDiffUpdatedEvent`
- `TurnCompletedEvent`
- `TurnFailedEvent`
- `TurnInterruptedEvent`

observe notice 的识别规则也已经统一成：

- `provider_payload["observe"] == true`
- 或 `provider_payload["classification"] == "observe"`

不再依赖旧的 `fallback` 字段名。

## 当前设计边界

### 明确进入主路径的消息

- assistant 文本增量与完成态
- reasoning 增量
- plan 更新
- tool 生命周期与输出
- approval resolved
- usage 更新
- thread / turn 生命周期
- thread status / skills / diff / rate limits 等系统状态
- terminal interaction

### 明确不进入主路径的消息

- `userMessage` 回声
- `item/reasoning/summaryPartAdded`
- 未知 method 的正式状态推进

### unknown event 的统一处理

unknown event 的目标不是“尽量猜”，而是：

- 不影响已知主路径
- 不导致卡死
- 不吞掉排查信息

因此当前统一策略是：

1. 保留 method。
2. 保留完整 payload。
3. 生成 observe notice。
4. 让上层 transcript / 调试视图能直接看到。

## 为什么这是小范围重构，不是补丁

这次收敛没有去改 `agent_runtime -> presentation` 的公共接口，而是在 `codex_adapter` 内部把职责重新摆正：

- transport 只做 transport
- mapper 只做编排
- registry 只做声明
- semantic mapper 只做 provider 语义收敛
- runtime projector 只做统一事件投影

这样后续如果官方 typed schema 再补充新 method，通常只需要：

1. 在 `event_registry.py` 增加一条注册。
2. 在 `semantic_mapper.py` 增加对应映射。
3. 如果需要 UI / 状态消费，再在 `runtime_projector.py` 和 reducer 中补一条统一语义。

而不是重新打开一条第二消费链。

## 后续建议

下一阶段最值得做的不是再删代码，而是做真实 schema 验证：

1. 用更多 `codex 0.115.x` 样本确认 registry 覆盖面。
2. 核对 `terminal.interaction`、`turn/diff/updated`、`skills/changed` 的真实 payload 形状。
3. 如果某些 observe notice 已经稳定出现，再决定是否把它们升级为正式语义事件。
