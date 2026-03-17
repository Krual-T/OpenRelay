# Agent Runtime Relay

更新时间：2026-03-16

## 背景

`openrelay` 现在已经把 Feishu 侧聊天体验收敛到“远程 coding agent 壳”这个方向，但运行时骨架仍然偏向“针对 Codex 单独适配”。

这在短期内能工作，但有两个明显问题：

- 如果继续围绕 `codex app-server` 的 method / item type 直接堆运行时逻辑，后续接入 Claude Code 时会被迫重写主路径。
- 如果 Feishu 的目标体验是“尽量像原生 TUI”，系统真正应该抽象的不是某个 backend 的协议，而是 **agent 运行时语义**：会话、回合、流式回复、工具执行、审批、中断、历史投影。

因此需要先定义一套 backend-neutral 的 runtime 模型，再让 Codex 和未来的 Claude Code 通过各自 adapter 接入。

## 目标

这份文档回答六个问题：

- `openrelay` 的核心运行时边界应该如何定义
- Feishu 应该和 backend 保持什么关系
- Codex 与未来 Claude Code 应该落在什么抽象层
- 统一运行时模型需要哪些类与方法
- presenter / interaction / session binding 应该如何解耦
- 从当前仓库迁移到新结构时，主路径应先收敛哪些部分

## 非目标

这份文档不讨论下面这些问题：

- 飞书卡片视觉样式的具体配色或排版
- Claude Code 的真实协议细节
- 一次性替换整个仓库的 patch 方案
- provider feature parity 的最终 UI 呈现细节

## 结论

`openrelay` 应收敛到下面这条主线：

- **Feishu 是统一的 agent runtime relay，不是某个 backend 的专用客户端**
- **backend adapter 负责把 provider 协议翻译成统一 runtime event**
- **runtime 主层只理解会话、回合、流式文本、工具、审批、完成态，不直接理解 Codex item method**
- **presentation 只消费统一 view model，不直接依赖 backend schema**
- **Codex 是第一个 adapter，Claude Code 未来作为第二个 adapter 接入**

一句话概括：

> 不要把 openrelay 设计成 Codex app-server relay，而要把它设计成统一 agent runtime relay，其中 Codex 只是第一个 backend。

## 总体结构

建议把系统收敛成六层：

1. backend adapter
2. runtime event / reducer
3. session binding / persistence
4. interaction / approval controller
5. presentation model
6. feishu transport

建议目录：

- `src/openrelay/agent_runtime/`
- `src/openrelay/backends/codex_adapter/`
- `src/openrelay/backends/claude_adapter/`
- `src/openrelay/session/`
- `src/openrelay/runtime/interactions/`
- `src/openrelay/presentation/`

## 核心原则

### 1. 抽象运行时语义，不抽象 provider method

不应把系统主接口设计成：

- `thread/start`
- `turn/start`
- `item/completed`

因为这些命名会把 Codex 的协议细节泄漏到 runtime 主层。

应抽象成：

- session
- turn
- assistant delta
- tool state
- approval request
- turn completed / failed / interrupted

### 2. provider-specific 信息保留，但不上浮为主路径

Codex 或未来 Claude Code 可能会暴露不同元信息：

- compact
- reasoning 原文
- 特定 tool metadata
- 独有 approval payload

这些信息应该允许通过 `provider_payload` 保留，但不应破坏统一主模型。

### 3. Feishu 只投影，不解释

Feishu 层不应理解：

- `item/agentMessage/delta`
- `item/fileChange/requestApproval`
- `thread/tokenUsage/updated`

Feishu 层只应理解统一后的：

- assistant_text
- running tools
- pending approval
- usage
- turn status

### 4. 用户可见身份是 backend session

系统内部可以保留 relay binding，但用户可见主身份应始终是：

- `backend`
- `native_session_id`

不要让本地临时 `session_id` 重新长成产品语义。

## 统一领域模型

建议新建 `src/openrelay/agent_runtime/models.py`。

### `BackendKind`

职责：

- 表示 backend 类型

建议定义：

```python
type BackendKind = Literal["codex", "claude"]
```

### `SessionLocator`

职责：

- 唯一定位 backend 原生会话

建议字段：

- `backend: BackendKind`
- `native_session_id: str`

### `SessionSummary`

职责：

- 用于 `/resume`、会话列表、面板展示

建议字段：

- `backend: BackendKind`
- `native_session_id: str`
- `title: str`
- `preview: str`
- `cwd: str`
- `updated_at: str`
- `status: str`
- `metadata: dict[str, Any]`

### `TranscriptMessage`

职责：

- 会话历史中的最小消息投影

建议字段：

- `role: Literal["user", "assistant", "system"]`
- `text: str`
- `created_at: str | None = None`

### `SessionTranscript`

职责：

- 统一会话历史读取结果

建议字段：

- `summary: SessionSummary`
- `messages: tuple[TranscriptMessage, ...]`
- `metadata: dict[str, Any]`

### `TurnInput`

职责：

- 统一一轮输入，不直接暴露 provider 参数名

建议字段：

- `text: str`
- `local_image_paths: tuple[str, ...]`
- `cwd: str`
- `model: str | None`
- `safety_mode: str`
- `output_schema: dict[str, Any] | None`
- `metadata: dict[str, Any]`

### `ApprovalRequest`

职责：

- 统一审批语义

建议字段：

- `approval_id: str`
- `session_id: str`
- `turn_id: str`
- `kind: Literal["command", "file_change", "permissions", "user_input", "custom"]`
- `title: str`
- `description: str`
- `payload: dict[str, Any]`
- `options: tuple[str, ...]`
- `provider_payload: dict[str, Any]`

### `ApprovalDecision`

职责：

- 统一审批响应

建议字段：

- `decision: Literal["accept", "accept_for_session", "decline", "cancel", "custom"]`
- `payload: dict[str, Any]`

### `ToolState`

职责：

- 统一表示一个运行中的工具项

建议字段：

- `tool_id: str`
- `kind: Literal["command", "file_change", "web_search", "mcp", "review", "custom"]`
- `title: str`
- `status: Literal["pending", "running", "completed", "failed", "declined"]`
- `preview: str`
- `detail: str`
- `exit_code: int | None`
- `provider_payload: dict[str, Any]`

### `PlanStep`

职责：

- 统一 plan 展示

建议字段：

- `step: str`
- `status: Literal["pending", "in_progress", "completed"]`

### `UsageSnapshot`

职责：

- 统一 token usage 展示

建议字段：

- `input_tokens: int | None`
- `cached_input_tokens: int | None`
- `output_tokens: int | None`
- `reasoning_output_tokens: int | None`
- `total_tokens: int | None`
- `context_window: int | None`

## 统一事件模型

建议新建 `src/openrelay/agent_runtime/events.py`。

所有 backend protocol 都先映射成统一事件，再进入 reducer。

### `RuntimeEvent`

职责：

- 作为统一事件基类

建议字段：

- `backend: BackendKind`
- `session_id: str`
- `turn_id: str`
- `event_type: str`
- `created_at: str`
- `provider_payload: dict[str, Any]`

### 建议事件子类

#### `SessionStartedEvent`

字段：

- `native_session_id: str`
- `title: str`

#### `TurnStartedEvent`

字段：

- 无新增字段

#### `AssistantDeltaEvent`

字段：

- `delta: str`

#### `AssistantCompletedEvent`

字段：

- `text: str`

#### `ReasoningDeltaEvent`

字段：

- `text: str`

#### `PlanUpdatedEvent`

字段：

- `steps: tuple[PlanStep, ...]`
- `explanation: str`

#### `ToolStartedEvent`

字段：

- `tool: ToolState`

#### `ToolProgressEvent`

字段：

- `tool_id: str`
- `detail: str`

#### `ToolCompletedEvent`

字段：

- `tool: ToolState`

#### `ApprovalRequestedEvent`

字段：

- `request: ApprovalRequest`

#### `ApprovalResolvedEvent`

字段：

- `approval_id: str`

#### `UsageUpdatedEvent`

字段：

- `usage: UsageSnapshot`

#### `TurnCompletedEvent`

字段：

- `final_text: str`
- `usage: UsageSnapshot | None`

#### `TurnFailedEvent`

字段：

- `message: str`

#### `TurnInterruptedEvent`

字段：

- `message: str`

#### `BackendNoticeEvent`

字段：

- `level: Literal["info", "warning", "error"]`
- `message: str`

## Backend 抽象接口

建议新建 `src/openrelay/agent_runtime/backend.py`。

### `AgentBackend`

职责：

- 统一 backend 能力边界

建议方法：

```python
class AgentBackend(Protocol):
    def name(self) -> BackendKind: ...

    def capabilities(self) -> BackendCapabilities: ...

    async def start_session(
        self,
        request: StartSessionRequest,
    ) -> SessionSummary: ...

    async def resume_session(
        self,
        locator: SessionLocator,
    ) -> SessionSummary: ...

    async def list_sessions(
        self,
        request: ListSessionsRequest,
    ) -> tuple[list[SessionSummary], str]: ...

    async def read_session(
        self,
        locator: SessionLocator,
    ) -> SessionTranscript: ...

    async def start_turn(
        self,
        locator: SessionLocator,
        turn_input: TurnInput,
        sink: RuntimeEventSink,
    ) -> RunningTurnHandle: ...

    async def interrupt_turn(
        self,
        locator: SessionLocator,
        turn_id: str,
    ) -> None: ...

    async def resolve_approval(
        self,
        locator: SessionLocator,
        approval: ApprovalDecision,
        request: ApprovalRequest,
    ) -> None: ...

    async def compact_session(
        self,
        locator: SessionLocator,
    ) -> dict[str, Any]: ...

    async def shutdown(self) -> None: ...
```

### `BackendCapabilities`

职责：

- 显式声明 backend feature surface

建议字段：

- `supports_session_list: bool`
- `supports_session_read: bool`
- `supports_compact: bool`
- `supports_output_schema: bool`
- `supports_plan_updates: bool`
- `supports_reasoning_stream: bool`
- `supports_file_change_approval: bool`
- `supports_command_approval: bool`

### `StartSessionRequest`

职责：

- 统一启动新会话所需参数

建议字段：

- `cwd: str`
- `model: str | None`
- `safety_mode: str`
- `metadata: dict[str, Any]`

### `ListSessionsRequest`

职责：

- 会话列表查询参数

建议字段：

- `limit: int`
- `cursor: str`
- `cwd: str | None`

### `RuntimeEventSink`

职责：

- 统一事件出口

建议方法：

```python
class RuntimeEventSink(Protocol):
    async def publish(self, event: RuntimeEvent) -> None: ...
```

### `RunningTurnHandle`

职责：

- 表示已启动的一轮 turn

建议字段：

- `session_id: str`
- `turn_id: str`
- `backend: BackendKind`

建议方法：

- `async def wait(self) -> None`

## Codex adapter 设计

建议新建目录 `src/openrelay/backends/codex_adapter/`。

Codex adapter 不应再把 transport、协议映射、会话 API、turn 状态都堆在单个类里。

### `CodexRpcTransport`

文件：

- `src/openrelay/backends/codex_adapter/transport.py`

职责：

- 拉起 `codex app-server`
- 管理 JSON-RPC request / response
- 分发 notification 与 server request
- 不做 UI 语义归约

建议字段：

- `codex_path: str`
- `workspace_root: Path`
- `sqlite_home: Path`
- `process: Process | None`
- `pending_requests: dict[int | str, asyncio.Future[Any]]`
- `notification_subscribers: list[Callable[[str, dict[str, Any]], Awaitable[None]]]`
- `server_request_subscribers: list[Callable[[RequestEnvelope], Awaitable[bool]]]`

建议方法：

- `async def start(self) -> None`
- `async def stop(self) -> None`
- `async def ensure_started(self) -> None`
- `async def request(self, method: str, params: dict[str, Any], *, cancel_event: asyncio.Event | None = None) -> Any`
- `async def send_result(self, request_id: int | str, result: dict[str, Any]) -> None`
- `async def send_error(self, request_id: int | str, code: int, message: str, data: Any = None) -> None`
- `def subscribe_notifications(self, callback: Callable[[str, dict[str, Any]], Awaitable[None]]) -> None`
- `def subscribe_server_requests(self, callback: Callable[[RequestEnvelope], Awaitable[bool]]) -> None`

内部私有方法建议：

- `_start_process`
- `_read_stdout_loop`
- `_read_stderr_loop`
- `_handle_message`
- `_write_message`
- `_next_request_id`

### `CodexProtocolMapper`

文件：

- `src/openrelay/backends/codex_adapter/mapper.py`

职责：

- 只做 `codex app-server v2` 到统一模型的翻译
- 不持有运行状态
- 未来如果需要兼容旧 `codex/event/*`，也应放在这个层，不上浮到 runtime 主层

建议方法：

- `def build_thread_start_params(self, request: StartSessionRequest) -> dict[str, Any]`
- `def build_thread_resume_params(self, locator: SessionLocator) -> dict[str, Any]`
- `def build_turn_start_params(self, native_session_id: str, turn_input: TurnInput) -> dict[str, Any]`
- `def map_session_summary(self, payload: dict[str, Any]) -> SessionSummary`
- `def map_session_transcript(self, payload: dict[str, Any]) -> SessionTranscript`
- `def map_notification(self, method: str, params: dict[str, Any], session_id: str, turn_id_hint: str = "") -> list[RuntimeEvent]`
- `def map_server_request(self, request_id: str, method: str, params: dict[str, Any], session_id: str) -> ApprovalRequest | None`
- `def build_approval_response(self, request: ApprovalRequest, decision: ApprovalDecision) -> dict[str, Any]`

注意：

- 这里不做 presentation 文案拼装
- 只做协议字段归一化

### `CodexSessionClient`

文件：

- `src/openrelay/backends/codex_adapter/client.py`

职责：

- 对外暴露 session / turn 高层 API
- 依赖 transport 与 mapper
- 把 Codex 协议适配成 `AgentBackend` 所需能力

建议字段：

- `transport: CodexRpcTransport`
- `mapper: CodexProtocolMapper`
- `active_turns: dict[str, CodexTurnStream]`

建议方法：

- `async def start_session(self, request: StartSessionRequest) -> SessionSummary`
- `async def resume_session(self, locator: SessionLocator) -> SessionSummary`
- `async def list_sessions(self, request: ListSessionsRequest) -> tuple[list[SessionSummary], str]`
- `async def read_session(self, locator: SessionLocator) -> SessionTranscript`
- `async def start_turn(self, locator: SessionLocator, turn_input: TurnInput, sink: RuntimeEventSink) -> RunningTurnHandle`
- `async def interrupt_turn(self, locator: SessionLocator, turn_id: str) -> None`
- `async def resolve_approval(self, locator: SessionLocator, approval: ApprovalDecision, request: ApprovalRequest) -> None`
- `async def compact_session(self, locator: SessionLocator) -> dict[str, Any]`

### `CodexTurnStream`

文件：

- `src/openrelay/backends/codex_adapter/turn_stream.py`

职责：

- 管理单轮 turn 的生命周期
- 跟踪 turn_id、pending approval、active tool state
- 收到 transport 事件后，经 mapper 转成统一 event 并发布给 sink

建议字段：

- `session_id: str`
- `native_session_id: str`
- `turn_id: str`
- `sink: RuntimeEventSink`
- `mapper: CodexProtocolMapper`
- `pending_approvals: dict[str, ApprovalRequest]`
- `done: bool`

建议方法：

- `async def bind_started_turn(self, turn_id: str) -> None`
- `async def handle_notification(self, method: str, params: dict[str, Any]) -> None`
- `async def handle_server_request(self, envelope: RequestEnvelope) -> bool`
- `async def mark_done(self) -> None`

### `CodexAdapter`

文件：

- `src/openrelay/backends/codex_adapter/adapter.py`

职责：

- 实现 `AgentBackend`
- 负责 client 生命周期与 scope 维度复用

建议字段：

- `clients_by_scope: dict[tuple[str, str], CodexSessionClient]`

建议方法：

- `def name(self) -> BackendKind`
- `def capabilities(self) -> BackendCapabilities`
- `async def start_session(...) -> SessionSummary`
- `async def resume_session(...) -> SessionSummary`
- `async def list_sessions(...) -> tuple[list[SessionSummary], str]`
- `async def read_session(...) -> SessionTranscript`
- `async def start_turn(...) -> RunningTurnHandle`
- `async def interrupt_turn(...) -> None`
- `async def resolve_approval(...) -> None`
- `async def compact_session(...) -> dict[str, Any]`
- `async def shutdown(self) -> None`

## Claude adapter 预留结构

建议新建目录 `src/openrelay/backends/claude_adapter/`。

即使暂时不实现，也应预留与 Codex 同构的结构：

- `ClaudeTransport`
- `ClaudeProtocolMapper`
- `ClaudeSessionClient`
- `ClaudeTurnStream`
- `ClaudeAdapter`

这样做的原因不是“看起来整齐”，而是为了强制 Claude 也输出同样的统一 runtime model，而不是让第二个 backend 再次绕过抽象层。

约束如下：

- `ClaudeAdapter` 必须实现 `AgentBackend`
- Claude 特有信息只能放在 `provider_payload`
- presenter 与 reducer 不得出现 `if backend == "claude"` 的主路径分支

允许差异存在的位置只有：

- `capabilities()`
- provider mapper
- provider approval payload

## 统一 reducer

建议新建 `src/openrelay/agent_runtime/reducer.py`。

### `LiveTurnViewModel`

职责：

- 作为飞书展示与状态查询的唯一来源

建议字段：

- `backend: BackendKind`
- `session_id: str`
- `native_session_id: str`
- `turn_id: str`
- `status: Literal["idle", "running", "completed", "failed", "interrupted"]`
- `assistant_text: str`
- `reasoning_text: str`
- `plan_steps: tuple[PlanStep, ...]`
- `tools: tuple[ToolState, ...]`
- `pending_approval: ApprovalRequest | None`
- `usage: UsageSnapshot | None`
- `error_message: str`
- `updated_at: str`

### `LiveTurnReducer`

职责：

- 输入统一 event
- 输出新的 turn view model

建议字段：

- `state: LiveTurnViewModel`

建议方法：

- `def apply(self, event: RuntimeEvent) -> LiveTurnViewModel`
- `def _apply_assistant_delta(self, event: AssistantDeltaEvent) -> None`
- `def _apply_assistant_completed(self, event: AssistantCompletedEvent) -> None`
- `def _apply_reasoning_delta(self, event: ReasoningDeltaEvent) -> None`
- `def _apply_plan_updated(self, event: PlanUpdatedEvent) -> None`
- `def _apply_tool_started(self, event: ToolStartedEvent) -> None`
- `def _apply_tool_progress(self, event: ToolProgressEvent) -> None`
- `def _apply_tool_completed(self, event: ToolCompletedEvent) -> None`
- `def _apply_approval_requested(self, event: ApprovalRequestedEvent) -> None`
- `def _apply_approval_resolved(self, event: ApprovalResolvedEvent) -> None`
- `def _apply_usage_updated(self, event: UsageUpdatedEvent) -> None`
- `def _apply_turn_completed(self, event: TurnCompletedEvent) -> None`
- `def _apply_turn_failed(self, event: TurnFailedEvent) -> None`
- `def _apply_turn_interrupted(self, event: TurnInterruptedEvent) -> None`

要求：

- 未知 event 不能让 reducer 失败
- 同一 `tool_id` 的多次事件必须被合并为单个 tool state
- `turn/completed` 之类终态事件必须是 status 的唯一终结入口

### `LiveTurnRegistry`

职责：

- 管理多个 reducer

建议字段：

- `reducers: dict[tuple[str, str], LiveTurnReducer]`

建议方法：

- `def get_or_create(self, session_id: str, turn_id: str, backend: BackendKind, native_session_id: str) -> LiveTurnReducer`
- `def apply(self, event: RuntimeEvent) -> LiveTurnViewModel`
- `def read(self, session_id: str, turn_id: str) -> LiveTurnViewModel | None`
- `def clear_finished(self, older_than_seconds: int) -> None`

## Session Binding 层

建议放在 `src/openrelay/session/`。

### `RelaySessionBinding`

文件：

- `src/openrelay/session/models.py`

职责：

- 表示飞书 scope 与 backend session 的绑定关系

建议字段：

- `relay_session_id: str`
- `backend: BackendKind`
- `native_session_id: str`
- `cwd: str`
- `model: str`
- `safety_mode: str`
- `feishu_chat_id: str`
- `feishu_thread_id: str`
- `created_at: str`
- `updated_at: str`

### `SessionBindingStore`

文件：

- `src/openrelay/session/store.py`

职责：

- 存储并查询 relay session binding

建议方法：

- `def save(self, binding: RelaySessionBinding) -> None`
- `def get(self, relay_session_id: str) -> RelaySessionBinding | None`
- `def find_by_feishu_scope(self, chat_id: str, thread_id: str) -> RelaySessionBinding | None`
- `def list_recent(self, backend: BackendKind | None = None, limit: int = 20) -> list[RelaySessionBinding]`
- `def update_native_session_id(self, relay_session_id: str, native_session_id: str) -> None`

## Runtime 主服务

建议新建 `src/openrelay/agent_runtime/service.py`。

### `RuntimeEventHub`

职责：

- 发布 runtime event 给多个消费者

建议字段：

- `subscribers: list[RuntimeEventSubscriber]`

建议方法：

- `async def publish(self, event: RuntimeEvent) -> None`
- `def subscribe(self, subscriber: RuntimeEventSubscriber) -> None`

### `AgentRuntimeService`

职责：

- 编排 backend、binding、reducer、interaction controller
- 向 runtime command 与 message handling 暴露统一入口

建议字段：

- `backends: dict[BackendKind, AgentBackend]`
- `bindings: SessionBindingStore`
- `turn_registry: LiveTurnRegistry`
- `event_hub: RuntimeEventHub`
- `interaction_controller: InteractionController`

建议方法：

- `async def start_new_session(self, backend: BackendKind, request: StartSessionRequest, scope: RelayScope) -> RelaySessionBinding`
- `async def resume_session(self, locator: SessionLocator, scope: RelayScope) -> RelaySessionBinding`
- `async def list_sessions(self, backend: BackendKind, request: ListSessionsRequest) -> tuple[list[SessionSummary], str]`
- `async def read_session(self, locator: SessionLocator) -> SessionTranscript`
- `async def run_turn(self, binding: RelaySessionBinding, turn_input: TurnInput) -> LiveTurnViewModel`
- `async def interrupt_turn(self, binding: RelaySessionBinding, turn_id: str) -> None`
- `async def resolve_approval(self, binding: RelaySessionBinding, request: ApprovalRequest, decision: ApprovalDecision) -> None`
- `async def compact_session(self, binding: RelaySessionBinding) -> dict[str, Any]`

内部私有方法建议：

- `_select_backend`
- `_make_event_sink`
- `_on_runtime_event`

## Interaction / Approval 层

建议继续放在 `src/openrelay/runtime/interactions/`，但语义边界要收敛。

### `InteractionController`

职责：

- 跟踪 pending approval
- 把飞书按钮输入转换成统一审批决策
- 在 approval resolved 后清理状态

建议字段：

- `pending_requests: dict[str, ApprovalRequest]`

建议方法：

- `def remember(self, request: ApprovalRequest) -> None`
- `def resolve(self, approval_id: str) -> ApprovalRequest | None`
- `def get(self, approval_id: str) -> ApprovalRequest | None`
- `def list_for_turn(self, session_id: str, turn_id: str) -> list[ApprovalRequest]`

### `ApprovalDecisionFactory`

职责：

- 统一生成标准审批决策

建议方法：

- `def accept(self) -> ApprovalDecision`
- `def accept_for_session(self) -> ApprovalDecision`
- `def decline(self) -> ApprovalDecision`
- `def cancel(self) -> ApprovalDecision`
- `def custom(self, payload: dict[str, Any]) -> ApprovalDecision`

## Presentation 层

presentation 层不能直接消费 backend schema，只能消费 `LiveTurnViewModel`。

建议文件：`src/openrelay/presentation/runtime_status.py`

### `TurnPresentationModel`

职责：

- 表示一个 turn 的最终展示结构

建议字段：

- `title: str`
- `body_text: str`
- `status_text: str`
- `reasoning_text: str`
- `plan_lines: tuple[str, ...]`
- `tool_blocks: tuple[ToolPresentationBlock, ...]`
- `approval_block: ApprovalPresentationBlock | None`
- `footer_lines: tuple[str, ...]`

### `ToolPresentationBlock`

建议字段：

- `title: str`
- `status: str`
- `preview: str`
- `detail: str`

### `ApprovalPresentationBlock`

建议字段：

- `title: str`
- `description: str`
- `actions: tuple[str, ...]`

### `TurnPresentationMapper`

职责：

- 从 `LiveTurnViewModel` 映射到最终展示模型

建议方法：

- `def map_live_turn(self, state: LiveTurnViewModel) -> TurnPresentationModel`
- `def _map_tools(self, state: LiveTurnViewModel) -> tuple[ToolPresentationBlock, ...]`
- `def _map_approval(self, state: LiveTurnViewModel) -> ApprovalPresentationBlock | None`
- `def _build_footer(self, state: LiveTurnViewModel) -> tuple[str, ...]`

## Feishu 投影层

Feishu 层不关心 backend 类型，也不关心 provider method。

### `FeishuTurnPresenter`

文件：

- `src/openrelay/feishu/presenter.py`

职责：

- 把 `TurnPresentationModel` 转成飞书卡片 payload

建议方法：

- `def render_running(self, model: TurnPresentationModel) -> dict[str, Any]`
- `def render_completed(self, model: TurnPresentationModel) -> dict[str, Any]`
- `def render_failed(self, model: TurnPresentationModel) -> dict[str, Any]`
- `def render_interrupted(self, model: TurnPresentationModel) -> dict[str, Any]`

### `FeishuTurnPublisher`

文件：

- `src/openrelay/feishu/publisher.py`

职责：

- 控制首次发送、增量更新、节流、终态落版

建议方法：

- `async def open_turn(self, scope: RelayScope, model: TurnPresentationModel) -> PublishedMessageRef`
- `async def update_turn(self, ref: PublishedMessageRef, model: TurnPresentationModel) -> None`
- `async def finalize_turn(self, ref: PublishedMessageRef, model: TurnPresentationModel) -> None`

## 事件收敛策略

为了避免继续把协议复杂度搬进系统主路径，建议明确收敛边界。

### 第一阶段必须支持

不论 backend 如何，主路径至少应覆盖：

- session start / resume
- turn start
- assistant text delta
- tool item started / completed
- approval request / resolve
- turn completed / failed / interrupted
- session read / list

### 第二阶段增强项

可以在主路径稳定后追加：

- reasoning delta
- plan updated
- usage updated
- web search
- MCP progress
- turn diff aggregation

### 一律不进入第一阶段主路径

- experimental provider-only features
- plugin / app marketplace
- realtime audio
- provider config 编辑接口

## 对 Codex 场景的直接含义

如果以这套结构落地，Codex 只是第一个 backend：

- `CodexRpcTransport` 负责 stdio JSON-RPC
- `CodexProtocolMapper` 负责把 `codex app-server v2` method 映射成统一 event
- `CodexAdapter` 实现统一 backend 接口
- reducer / presenter / interaction controller 完全不需要知道 `item/agentMessage/delta`

这意味着：

- Codex 可以先把现有实现收敛成 adapter
- 未来 Claude Code 只需要新增 adapter，而不是重写飞书主层

## 对 Claude Code 接入的直接约束

为了防止第二个 backend 接进来后破坏结构，建议现在就把下面三条定死：

- presenter 不得直接使用 provider-specific event name
- runtime service 不得包含 `if backend == "codex"` 的主路径分支
- backend 之间的差异只能体现在 adapter、capabilities、provider payload

## 迁移顺序建议

为了避免一次性推翻重做，建议按下面顺序迁移。

### Phase 1：先建统一 runtime model

新增：

- `agent_runtime/models.py`
- `agent_runtime/events.py`
- `agent_runtime/backend.py`
- `agent_runtime/reducer.py`

这一步先不动 Feishu 展示，只把统一 contract 定下来。

### Phase 2：把 Codex 现有实现压缩进 adapter

新增：

- `backends/codex_adapter/transport.py`
- `backends/codex_adapter/mapper.py`
- `backends/codex_adapter/client.py`
- `backends/codex_adapter/turn_stream.py`
- `backends/codex_adapter/adapter.py`

然后让旧的 `src/openrelay/backends/codex.py` 逐步退化为兼容壳或直接删除。

### Phase 3：runtime 主层改用统一 service

新增：

- `agent_runtime/service.py`
- `session/store.py`

然后让现有 runtime command / reply orchestration 改调 `AgentRuntimeService`。

### Phase 4：presentation 与 feishu 解耦

新增：

- `presentation/runtime_status.py`
- `feishu/presenter.py`
- `feishu/publisher.py`

把飞书展示收敛到只吃 `TurnPresentationModel`。

### Phase 5：再接 Claude adapter

当上面四层稳定后，再新增：

- `backends/claude_adapter/`

这样第二个 backend 的引入只会改变 adapter，不会再次撕开 runtime 主结构。

## 最小落地版本

如果要避免一开始又做过度抽象，第一版建议只落这些类：

- `AgentBackend`
- `BackendCapabilities`
- `RuntimeEvent`
- `LiveTurnViewModel`
- `LiveTurnReducer`
- `LiveTurnRegistry`
- `AgentRuntimeService`
- `SessionBindingStore`
- `InteractionController`
- `TurnPresentationMapper`
- `CodexRpcTransport`
- `CodexProtocolMapper`
- `CodexSessionClient`
- `CodexAdapter`

并且 Codex 第一版只强制支持下面这些通知：

- `turn/started`
- `item/agentMessage/delta`
- `item/started`
- `item/completed`
- `turn/plan/updated`
- `thread/tokenUsage/updated`
- `turn/completed`
- approval request / resolved

其余事件先走可选增强。

## 实现补充附录

下面这些内容用于把设计文档从“架构方向”补到“可直接开工的第一阶段实现约束”。

补充原则：

- 不追求一次性把全部 provider 细节写成最终规范。
- 只把 Phase 1 到 Phase 3 真正会阻塞实现的边界定死。
- 约束以当前仓库可验证证据为准；legacy `src/openrelay/backends/codex.py`、`src/openrelay/runtime/live.py`、`tests/test_codex_backend.py` 已在后续收敛中删除，相关职责已迁入 `codex_adapter/`、`LiveTurnPresenter` 和更聚焦的 runtime/adapter 测试。

### Codex CLI 参考方式

虽然本地 `codex` 安装包主体是预编译二进制，无法直接从 TypeScript 源码阅读 TUI 实现，但从 `codex app-server` 暴露的协议面以及当前仓库已经验证过的消费路径，可以得出一个稳定结论：

- transport 层处理 JSON-RPC request / response / notification
- turn 层按 `threadId + turnId` 归属事件
- provider-specific method 会先归约成少量运行时状态变化
- 展示层消费的是“已归约状态”或“过程时间线”，而不是原始 method 名

第一阶段实现应保持这个方向，不把 Feishu 或 runtime 主层写成 app-server method switchboard。

### Codex 事件映射表

第一阶段 `CodexProtocolMapper` 必须至少覆盖下面这张映射表。

| app-server method | 条件 / 载荷 | 统一事件 | reducer / interaction 动作 |
| --- | --- | --- | --- |
| `turn/started` | 提取 `turn.id` | `TurnStartedEvent` | 建立 turn reducer；补全 `turn_id` |
| `thread/started` | 提取 `thread.id` | `SessionStartedEvent` | 更新 binding 的 `native_session_id` |
| `item/agentMessage/delta` | `itemId + delta` | `AssistantDeltaEvent` | 追加 assistant 文本 |
| `codex/event/agent_message_content_delta` | 旧别名；与上面去重 | `AssistantDeltaEvent` | 与 `item/agentMessage/delta` 视为同源事件 |
| `item/reasoning/textDelta` | `itemId + contentIndex + delta` | `ReasoningDeltaEvent` | 按 item 聚合 reasoning content |
| `codex/event/reasoning_content_delta` | 旧别名；与上面去重 | `ReasoningDeltaEvent` | 同上 |
| `item/reasoning/summaryTextDelta` | `itemId + summaryIndex + delta` | `ReasoningDeltaEvent` | 优先进入 reasoning summary 视图 |
| `codex/event/reasoning_summary_text_delta` | 旧别名；与上面去重 | `ReasoningDeltaEvent` | 同上 |
| `item/reasoning/summaryPartAdded` | 只标记 reasoning item 存在 | 无单独展示事件 | 只更新 mapper 内部聚合上下文 |
| `item/plan/delta` | 文本增量 | `BackendNoticeEvent` 或 `PlanUpdatedEvent` 前置缓冲 | 第一阶段允许只作为增量展示，不要求结构化 plan |
| `turn/plan/updated` | `plan[] + explanation` | `PlanUpdatedEvent` | 用结构化 steps 覆盖当前 plan |
| `item/commandExecution/outputDelta` | `itemId + delta` | `ToolProgressEvent` | 只更新 command detail，不直接发 UI 文本 |
| `codex/event/command_output_delta` | 旧别名 | `ToolProgressEvent` | 同上 |
| `item/commandExecution/terminalInteraction` | 终端交互请求 | `BackendNoticeEvent` | 第一阶段先保留到 `provider_payload`，不进主交互模型 |
| `item/fileChange/outputDelta` | patch / diff 输出 | `ToolProgressEvent` | 只更新 file-change detail |
| `item/mcpToolCall/progress` | 进度内容 | `ToolProgressEvent` | `kind="mcp"` |
| `item/started` | `item.type` | `ToolStartedEvent` 或 `BackendNoticeEvent` | `reasoning` / `commandExecution` / `webSearch` / `fileChange` / `collabAgentToolCall` 必须映射 |
| `codex/event/item_started` | 旧别名 | `ToolStartedEvent` 或 `BackendNoticeEvent` | 同上 |
| `item/completed` | `item.type` | `AssistantCompletedEvent` / `ToolCompletedEvent` / `PlanUpdatedEvent` | 按 item type 收口终态 |
| `codex/event/item_completed` | 旧别名 | 同上 | 同上 |
| `thread/tokenUsage/updated` | `tokenUsage.last` 或 `tokenUsage.total` | `UsageUpdatedEvent` | 更新 usage snapshot |
| `codex/event/token_count` | 旧别名 | `UsageUpdatedEvent` | 同上 |
| `serverRequest/resolved` | `requestId` | `ApprovalResolvedEvent` | 清理 pending approval |
| `turn/completed` | `turn.status` | `TurnCompletedEvent` / `TurnFailedEvent` / `TurnInterruptedEvent` | 统一 turn 终态出口 |
| `codex/event/task_complete` | 旧别名；兼容 `last_agent_message` | `TurnCompletedEvent` / `TurnFailedEvent` / `TurnInterruptedEvent` | 同上 |
| `error` | `willRetry != true` | `TurnFailedEvent` | 仅在不会重试时结束 turn |

### item type 到 tool kind 的最小映射

第一阶段只要求收敛下面这些 `item.type`：

| item.type | ToolState.kind | 展示约束 |
| --- | --- | --- |
| `commandExecution` | `command` | 标题和状态来自命令生命周期；输出增量进入 `detail` |
| `webSearch` | `web_search` | 只展示 query 摘要，不展示 provider 原始 action schema |
| `fileChange` | `file_change` | 展示文件列表与 add / update / delete 概要 |
| `collabAgentToolCall` | `custom` | 第一阶段保留 `tool` 和 agent 状态到 `provider_payload` |
| `mcpToolCall` | `mcp` | 只展示进度摘要 |
| `reasoning` | 不进入 `tools` 主列表 | reasoning 单独进入 `reasoning_text` |
| `agentMessage` | 不进入 `tools` 主列表 | 进入 assistant 文本 |
| `plan` | 不进入 `tools` 主列表 | 进入 `plan_steps` |

### server request 到审批模型的映射

第一阶段 `InteractionController` 必须覆盖下面这些 request method：

| server request method | ApprovalRequest.kind | 标准决策 |
| --- | --- | --- |
| `item/commandExecution/requestApproval` | `command` | `accept` / `accept_for_session` / `decline` / `cancel` |
| `item/fileChange/requestApproval` | `file_change` | `accept` / `decline` / `cancel` |
| `item/permissions/requestApproval` | `permissions` | `accept` / `accept_for_session` / `decline` / `cancel` |
| `item/tool/requestUserInput` | `user_input` | `custom(payload)` / `cancel` |
| `mcpServer/elicitation/request` | `user_input` | `custom(payload)` / `cancel` |

约束：

- runtime 主层只能看到 `ApprovalRequest` 和 `ApprovalDecision`，不能看到原始 method 名。
- provider-specific choice label、表单 schema、额外 payload 只保留在 `provider_payload`。
- `serverRequest/resolved` 必须成为清理 pending approval 的唯一确认信号；仅本地发出决策不视为已 resolved。

### 去重与归属规则

Codex adapter 第一阶段必须显式实现下面三条规则：

1. turn 归属以 `threadId + turnId` 为主，兼容旧消息里的 `conversationId + id`。
2. `item/agentMessage/delta` 与 `codex/event/agent_message_content_delta` 必须基于 `itemId + delta` 去重。
3. reasoning delta / summary delta 的新旧别名也必须去重，否则同一段 thinking 会重复渲染。

### 展示归约规则

为了贴近 Codex CLI 的实际消费方式，展示层只消费归约后的 turn 状态，不消费原始 protocol：

- assistant 文本只保留“当前已累积文本”与“最终完成文本”
- reasoning 只保留一个合并后的 `reasoning_text`
- tool 列表只保留用户可感知的工具状态，不外露 provider item 原始 schema
- approval 始终只有一个 `pending_approval` 主入口；如 provider 实际存在多请求，也在 interaction 层顺序化
- usage 只保留统一 token snapshot

换句话说，TUI / 卡片真正消费的是：

- `assistant_text`
- `reasoning_text`
- `plan_steps`
- `tools`
- `pending_approval`
- `usage`
- `turn status`

而不是：

- `item/agentMessage/delta`
- `item/completed`
- `thread/tokenUsage/updated`
- `item/fileChange/requestApproval`

### SessionRecord 到 RelaySessionBinding 的过渡

第一阶段不做数据库迁移工程；只做运行时收口。

过渡策略定为：

1. 继续复用现有 `StateStore` 持久化会话与消息。
2. 新增 `SessionBindingStore`，先作为 `StateStore` 的薄适配层，不单独引入第二套底层存储。
3. `RelaySessionBinding` 的最小字段来源如下：
   - `relay_session_id <- SessionRecord.session_id`
   - `backend <- SessionRecord.backend`
   - `native_session_id <- SessionRecord.native_session_id`
   - `cwd <- SessionRecord.cwd`
   - `model <- SessionRecord.model_override`
   - `safety_mode <- SessionRecord.safety_mode`
   - `feishu_chat_id / feishu_thread_id <- 由当前 session scope resolver 提供`
4. 当 `thread/started` 返回新的原生会话 id 时，只允许通过 binding store 更新，不再让 presentation 或 command service 直接写 `native_session_id`。

约束：

- 第一阶段不新造用户可见 session identity。
- `/resume`、面板和状态查询仍然以 backend + native session 为最终展示身份。
- 旧 `SessionRecord` 可以继续存在，但不能继续充当 runtime 主模型。

### RuntimeOrchestrator 的接线方式

第一阶段不删除现有 [src/openrelay/runtime/orchestrator.py](/home/Shaokun.Tang/Projects/openrelay/src/openrelay/runtime/orchestrator.py)，但它应退化为壳层协调器。

接线顺序定为：

1. `dispatch_message` 继续负责 Feishu 入站校验、去重和 scope 解析。
2. 会话加载后，orchestrator 不再直接调用 backend `run(...)` 语义，而是调用 `AgentRuntimeService.run_turn(...)`。
3. `AgentRuntimeService` 负责：
   - 选择 backend adapter
   - 建立 / 读取 session binding
   - 创建 event sink
   - 驱动 reducer
   - 把 approval request 注册到 interaction controller
4. Feishu streaming / reply card 只订阅 `LiveTurnViewModel` 或 `TurnPresentationModel`。

禁止事项：

- orchestrator 内部新增 provider-specific notification 分支
- presentation 层直接读取 app-server params
- interaction controller 直接向 Codex transport 写 JSON-RPC

### 第一阶段测试矩阵

第一阶段合入前，至少补齐或迁移下面这些测试：

| 测试主题 | 最低要求 |
| --- | --- |
| turn 归属 | 新旧 `threadId` / `conversationId` 载荷都能归到同一 turn |
| delta 去重 | agent / reasoning 新旧别名事件不会重复追加 |
| assistant streaming | `AssistantDeltaEvent` 能驱动增量文本，`TurnCompletedEvent` 能给出最终文本 |
| reasoning 聚合 | summary 与 content 的优先级稳定，最终只展示一份 reasoning 文本 |
| tool 生命周期 | `item/started` + `item/completed` 能收敛为单个 `ToolState` |
| approval 生命周期 | request -> 用户决策 -> `serverRequest/resolved` -> pending 清理 全链路成立 |
| token usage | `thread/tokenUsage/updated` 与旧 token alias 都能映射到统一 usage |
| turn 终态 | completed / interrupted / failed 都只能通过统一终态事件结束 reducer |
| binding 更新 | `thread/started` 返回新 session id 后，binding 会同步更新 |
| presenter 投影 | Feishu / runtime 展示只依赖统一 view model，不依赖 provider method |

### 第一阶段完成定义

满足下面四条，就可以认为文档已经足够支撑实现 Phase 1 到 Phase 3：

- Codex mapper 的最小事件表已定死。
- binding 过渡策略已定死。
- orchestrator 到 runtime service 的接线顺序已定死。
- 测试矩阵已定死。

## 预期结果

如果按这份方案推进，系统会得到四个长期收益：

- `openrelay` 的主路径从 provider protocol 中解耦，不再被 Codex schema 绑死。
- Feishu 展示层只投影统一运行时状态，后续换 backend 不需要重写 UI 主结构。
- Claude Code 接入会变成“新增 adapter”，而不是“重新设计 runtime”。
- 用户体验可以继续向“远程 TUI relay”靠近，而不是在多个 backend 之间长出不一致的产品语义。

## 当前落地结果

截至 2026-03-16，这份设计主线已经在代码中形成下面的稳定结构：

- runtime 主路径统一收敛到 `AgentRuntimeService -> AgentBackend -> RuntimeEvent -> LiveTurnReducer -> LiveTurnViewModel -> LiveTurnPresenter`
- Codex adapter 已收敛到 `src/openrelay/backends/codex_adapter/` 目录，旧 `src/openrelay/backends/codex.py` 已移入 `app_server.py` 并不再作为主路径模块暴露
- Claude 已以同构 `src/openrelay/backends/claude_adapter/` 目录接入，当前提供最小 turn 执行能力
- `/resume`、`/compact`、session presentation 与 panel 已改成 backend-neutral session 语义，不再把用户可见身份表述成 `Codex thread`
- runtime approval 主路径只保留 `ApprovalRequest -> ApprovalDecision`
- legacy live progress state machine、legacy runtime orchestrator 测试、legacy codex backend 测试都已删除

当前直接对应这份设计的主要代码锚点是：

- `src/openrelay/agent_runtime/`
- `src/openrelay/backends/codex_adapter/`
- `src/openrelay/backends/claude_adapter/`
- `src/openrelay/presentation/live_turn.py`
- `src/openrelay/runtime/turn.py`
- `src/openrelay/runtime/interactions/controller.py`

当前验证主线由下面这些测试覆盖：

- `tests/test_runtime_commands.py`
- `tests/test_resume_reply_behavior.py`
- `tests/test_runtime_help.py`
- `tests/test_runtime_interactions.py`
- `tests/test_live_turn_presenter.py`
- `tests/test_codex_protocol_mapper.py`
- `tests/test_codex_runtime_backend.py`
- `tests/test_claude_runtime_backend.py`
