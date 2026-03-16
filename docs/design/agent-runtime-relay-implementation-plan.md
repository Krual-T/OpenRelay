# Agent Runtime Relay Implementation Plan

更新时间：2026-03-16

## 目的

这份文档不重复 `docs/design/agent-runtime-relay.md` 的目标与原则，只回答一个更具体的问题：

- 当前仓库要怎样从“新旧双轨并存”收敛到统一 agent runtime 主路径
- 需要新增哪些类
- 哪些现有类应该修改、替换、删除
- 建议按什么顺序落地

本文默认 `docs/design/agent-runtime-relay.md` 仍然是主 design note。

## 当前判断

当前仓库已经完成了统一 runtime 的第一阶段：

- 已有 `agent_runtime` 领域模型、事件模型、reducer、service
- 已有 `session binding` 存储层
- 已有 `CodexProtocolMapper`
- 已有 `CodexRuntimeBackend`
- orchestrator / turn / `/resume` / `/compact` 已能接到 runtime service

但主路径仍未完全收敛，主要问题有四类：

1. `CodexRuntimeBackend` 仍然同时承担 adapter、turn lifecycle、approval pending、client 复用和 request 参数拼装。
2. `CodexProtocolMapper` 仍然持有 turn 内状态，不是纯 mapper。
3. runtime event 到 Feishu 展示前，仍会被翻译回 legacy progress dict。
4. presentation / interaction / command 层仍大量直接暴露 `Codex` 语义。

因此下一阶段不应继续叠补丁，而应做结构性收敛。

## 目标结构

目标主链路如下：

1. `AgentRuntimeService`
2. `AgentBackend`
3. `RuntimeEvent`
4. `LiveTurnReducer`
5. `LiveTurnViewModel`
6. `LiveTurnPresenter`
7. Feishu transport

约束：

- Feishu 层不再理解 provider method / item type
- runtime 主层不再把统一事件翻回 legacy progress event
- adapter 之外的层不再硬编码 `Codex`
- 第二个 backend 必须通过同构 adapter 目录接入

## 新增类

### `src/openrelay/backends/codex_adapter/transport.py`

新增 `CodexRpcTransport`

职责：

- 拉起并维护 `codex app-server`
- 管理 JSON-RPC request / response
- 向上分发 notification 与 server request
- 不承担 runtime 语义归约

建议字段：

- `codex_path: str`
- `workspace_root: Path`
- `sqlite_home: Path`
- `model: str`
- `safety_mode: str`
- `process: Process | None`
- `pending_requests: dict[int | str, asyncio.Future[Any]]`
- `notification_subscribers: list[Callable[[str, dict[str, Any]], Awaitable[None]]]`
- `server_request_subscribers: list[Callable[[int | str, str, dict[str, Any]], Awaitable[bool]]]`
- `request_timeout_seconds: float | None`
- `interrupt_grace_seconds: float`
- `resume_timeout_seconds: float`

建议方法：

- `async def start(self) -> None`
- `async def stop(self) -> None`
- `async def ensure_started(self) -> None`
- `async def request(self, method: str, params: dict[str, Any], *, cancel_event: asyncio.Event | None = None) -> Any`
- `async def send_result(self, request_id: int | str, result: dict[str, Any]) -> None`
- `async def send_error(self, request_id: int | str, code: int, message: str, data: Any = None) -> None`
- `def subscribe_notifications(self, callback: ...) -> None`
- `def subscribe_server_requests(self, callback: ...) -> None`

### `src/openrelay/backends/codex_adapter/client.py`

新增 `CodexSessionClient`

职责：

- 对外暴露 session / turn 高层 API
- 依赖 `CodexRpcTransport` 与 `CodexProtocolMapper`
- 管理 active turn stream

建议字段：

- `transport: CodexRpcTransport`
- `default_model: str`
- `mapper_factory: Callable[..., CodexProtocolMapper]`
- `active_turns: dict[str, CodexTurnStream]`

建议方法：

- `async def start_session(self, request: StartSessionRequest) -> SessionSummary`
- `async def resume_session(self, locator: SessionLocator) -> SessionSummary`
- `async def list_sessions(self, request: ListSessionsRequest) -> tuple[list[SessionSummary], str]`
- `async def read_session(self, locator: SessionLocator) -> SessionTranscript`
- `async def start_turn(self, locator: SessionLocator, turn_input: TurnInput, sink: RuntimeEventSink, session_id: str) -> RunningTurnHandle`
- `async def interrupt_turn(self, locator: SessionLocator, turn_id: str) -> None`
- `async def resolve_approval(self, locator: SessionLocator, approval: ApprovalDecision, request: ApprovalRequest) -> None`
- `async def compact_session(self, locator: SessionLocator) -> dict[str, Any]`
- `async def shutdown(self) -> None`

### `src/openrelay/backends/codex_adapter/turn_stream.py`

新增 `CodexTurnStream`

职责：

- 管理单轮 turn 生命周期
- 持有 turn 级状态
- 消费 transport 原始消息，经 mapper 翻译后发给 sink
- 管理 approval future 和 terminal state

建议字段：

- `session_id: str`
- `native_session_id: str`
- `turn_id: str`
- `sink: RuntimeEventSink`
- `mapper: CodexProtocolMapper`
- `pending_approvals: dict[str, asyncio.Future[dict[str, Any]]]`
- `future: asyncio.Future[None]`
- `done: bool`
- `interrupt_message: str`
- `interrupt_sent: bool`

建议方法：

- `async def bind_started_turn(self, turn_id: str) -> None`
- `async def handle_notification(self, method: str, params: dict[str, Any]) -> None`
- `async def handle_server_request(self, request_id: int | str, method: str, params: dict[str, Any]) -> bool`
- `async def resolve_approval(self, request: ApprovalRequest, decision: ApprovalDecision) -> None`
- `async def interrupt(self, transport: CodexRpcTransport) -> None`
- `def build_handle(self) -> RunningTurnHandle`

### `src/openrelay/backends/claude_adapter/`

新增同构目录：

- `transport.py`
- `mapper.py`
- `client.py`
- `adapter.py`

第一阶段可以先只提供最小占位实现，但必须满足：

- `ClaudeRuntimeBackend` 实现 `AgentBackend`
- Claude 特有信息只进入 `provider_payload`
- presentation / reducer / command 主路径不得出现 `if backend == "claude"` 的结构分支

### `src/openrelay/presentation/live_turn.py`

新增 `LiveTurnPresenter`

职责：

- 直接把 `LiveTurnViewModel` 投影成 Feishu streaming snapshot / process panel / final reply
- 取代当前 “runtime event -> legacy progress dict -> live state” 的桥接路径

建议方法：

- `def build_snapshot(self, state: LiveTurnViewModel) -> dict[str, Any]`
- `def build_process_text(self, state: LiveTurnViewModel) -> str`
- `def build_final_reply(self, state: LiveTurnViewModel) -> str`
- `def build_status_heading(self, state: LiveTurnViewModel) -> tuple[str, str]`

## 需要修改的类

### `src/openrelay/backends/codex_adapter/mapper.py`

目标：从“有状态协议归约器”收敛成“无状态协议 mapper”。

需要修改：

- 删除 turn 内状态字段：
  - `agent_text_by_id`
  - `command_output_by_id`
  - `file_change_output_by_id`
  - `reasoning_by_id`
  - `reasoning_order`
  - `usage`
  - `final_text`
- 把这些状态迁入 `CodexTurnStream`
- 保留纯转换职责：
  - request 参数构造
  - summary / transcript 映射
  - notification -> runtime event
  - server request -> `ApprovalRequest`
  - `ApprovalDecision` -> provider response

### `src/openrelay/backends/codex_adapter/backend.py`

目标：收敛成薄 adapter。

需要修改：

- 保留 `CodexRuntimeBackend` 作为 `AgentBackend` 实现
- 删除 turn 内状态与 approval pending 管理
- 删除直接拼 request 参数的职责
- 改为只管理 `clients_by_scope`
- 具体 session / turn 行为全部委托给 `CodexSessionClient`

### `src/openrelay/runtime/turn.py`

目标：去掉统一事件到 legacy progress dict 的回退桥。

需要修改：

- `BackendTurnSession.run_with_agent_runtime(...)` 不再订阅 event hub 后转旧 progress dict
- 运行时展示直接读取 `LiveTurnRegistry` 中的 `LiveTurnViewModel`
- 通过 `LiveTurnPresenter` 驱动 streaming card
- approval 入口改成统一 `request_approval(request: ApprovalRequest)`

### `src/openrelay/runtime/interactions/controller.py`

目标：interaction controller 改为统一审批层。

需要修改：

- `request(method, params)` 改成 `request_approval(request: ApprovalRequest)`
- 主逻辑根据 `ApprovalRequest.kind` 工作，而不是 provider method
- provider-specific 文案与 payload 解析下沉到 mapper
- 卡片文案去掉 `Codex` 硬编码

### `src/openrelay/runtime/commands.py`

目标：命令层不再承担 Codex 专用语义。

需要修改：

- `/resume`、`/compact` 成为 backend-neutral 的 session 操作
- 删除本地重复类型：
  - `NativeThreadSummary`
  - `NativeThreadMessage`
  - `NativeThreadDetails`
- 统一改用 `SessionSummary`、`SessionTranscript`、`TranscriptMessage`
- 删除对 legacy backend `list_threads/read_thread/compact_thread` 的主路径依赖
- 回复文案不再写死 “Codex 会话”

### `src/openrelay/runtime/panel_service.py`

目标：会话列表只走统一 runtime service。

需要修改：

- `_build_native_thread_list_payload(...)` 改成只消费 `runtime_service.list_sessions(...)`
- 删除 legacy native-thread backend 分支
- fallback 文案改为 backend-neutral

### `src/openrelay/presentation/session.py`

目标：会话卡片与 session presentation 去 Codex 语义化。

需要修改：

- `build_native_thread_list_card(...)` 改名为 `build_backend_session_list_card(...)`
- 标题与说明文案改为基于 backend 动态渲染
- 不再默认把用户可见身份称为 `thread`

### `src/openrelay/runtime/live.py`

目标：降级为纯格式化辅助，不再承担运行时主状态机。

需要修改：

- 删除或废弃 `apply_live_progress(...)` 主入口
- 删除 `Starting Codex`、`Connected native session` 等 provider 专属状态文案
- 如果保留文件，只保留 process panel / markdown 辅助函数

### `src/openrelay/runtime/orchestrator.py`

目标：最终主路径只保留 runtime backend。

需要修改：

- 删除旧 `Backend.run` 对 Codex 的主路径依赖
- 默认只装配 runtime backend
- `BackendTurnSession.run(...)` 最终只走 `AgentRuntimeService`
- backend 可用性判断基于 runtime backend 集合

### `src/openrelay/backends/registry.py`

目标：注册层只负责 runtime backend 描述与构造。

需要修改：

- 注册表不再围绕 legacy `Backend` 设计
- 至少预留 `claude` descriptor
- descriptor 与 orchestrator 一起只服务 runtime backend 主路径

### `src/openrelay/agent_runtime/reducer.py`

保留，但需要小幅修正：

- `clear_finished(...)` 应真正根据 `updated_at` 和阈值清理
- `ReasoningDeltaEvent` 的处理应支持增量而不是简单覆盖
- 类型标注应从 `backend: str` 收敛到 `BackendKind`

### `src/openrelay/agent_runtime/service.py`

保留，继续作为主编排层。

建议补充：

- `def make_sink(self) -> RuntimeEventSink`
- `def read_turn(self, session_id: str, turn_id: str) -> LiveTurnViewModel | None`
- 将 `interaction_controller` 从 tracker protocol 升级为统一审批接口

## 需要替换的类

### 用 `CodexRpcTransport + CodexSessionClient + CodexTurnStream` 替换当前 `CodexRuntimeBackend` 内部大部分实现

替换结果：

- `CodexRuntimeBackend` 变成薄适配层
- transport / session API / turn lifecycle / approval pending 分层明确

### 用 `LiveTurnPresenter` 替换当前基于 progress dict 的 live 渲染主路径

替换结果：

- Feishu 展示直接消费 `LiveTurnViewModel`
- runtime event 不再被翻译回 legacy event

### 用统一 `ApprovalRequest / ApprovalDecision` 流替换 interaction controller 的 provider-method 入口

替换结果：

- interaction 层只理解统一审批语义
- provider-specific payload 被限制在 adapter 内

## 需要删除的类或文件

### 删除 `src/openrelay/backends/codex.py`

删除前提：

- `CodexRpcTransport` 已完全接管 app-server 通信
- `CodexRuntimeBackend` 不再依赖 `CodexAppServerClient`

删除原因：

- 当前文件同时承担 transport、turn state、protocol mapping、approval bridge、thread API
- 它是现有双轨结构的主要来源

### 删除 `src/openrelay/runtime/turn.py` 中 runtime event -> legacy progress dict 的桥接逻辑

删除位置：

- `_handle_runtime_event(...)`
- `_runtime_tool_event(...)`
- 依赖旧 `apply_live_progress(...)` 的桥接路径

### 删除 `src/openrelay/runtime/commands.py` 里的本地 native thread DTO

删除对象：

- `NativeThreadSummary`
- `NativeThreadMessage`
- `NativeThreadDetails`

删除原因：

- 它们和统一 runtime 的 session / transcript DTO 重复

## 实施顺序

### 阶段 1：拆 Codex adapter

目标：

- 先把 `codex.py` 的职责拆开
- 不在这一阶段改变 Feishu 外部行为

步骤：

1. 新增 `transport.py`
2. 新增 `client.py`
3. 新增 `turn_stream.py`
4. 把 `backend.py` 收敛为薄 adapter
5. 让现有测试迁移到新结构

关闭信号：

- `src/openrelay/backends/codex.py` 不再被 runtime 主路径引用
- 当前状态：
  - 已落地 `src/openrelay/backends/codex_adapter/transport.py`
  - 已落地 `src/openrelay/backends/codex_adapter/client.py`
  - 已落地 `src/openrelay/backends/codex_adapter/turn_stream.py`
  - `src/openrelay/backends/codex_adapter/backend.py` 已收敛为薄 adapter
  - `src/openrelay/backends/codex_adapter/mapper.py` 已移出 turn 内聚合状态
  - runtime 主路径仍暂时通过 `CodexAppServerClient` 间接复用 `src/openrelay/backends/codex.py` 的 transport 实现，因此阶段 1 已完成“内部拆层”，但还没有达到“可删除 legacy transport 文件”的收尾状态

### 阶段 2：收敛 mapper 与 interaction

目标：

- 去掉 mapper 的内部状态
- interaction 改成统一审批语义

步骤：

1. 把 turn 内状态移到 `CodexTurnStream`
2. 重写 `RunInteractionController` 主接口
3. 让 approval 测试只依赖 `ApprovalRequest / ApprovalDecision`

关闭信号：

- interaction 层不再以 provider method 作为主入口
- 当前状态：
  - `src/openrelay/backends/codex_adapter/mapper.py` 已把 command / file_change / permissions / user_input 的统一字段写入 `ApprovalRequest.payload`
  - `src/openrelay/runtime/interactions/controller.py` 已新增 `request_approval(request: ApprovalRequest) -> ApprovalDecision`
  - `src/openrelay/runtime/turn.py` 的 runtime approval 路径已改为直接调用统一审批接口，不再在 turn 层解析 provider method
  - legacy `request(method, params)` 兼容入口仍保留给旧 backend context，因此阶段 2 目前完成了“runtime 主路径切换”，但还没完成 interaction 层的兼容代码清理

### 阶段 3：重写 live presentation 主路径

目标：

- 让 presentation 直接消费 `LiveTurnViewModel`

步骤：

1. 新增 `LiveTurnPresenter`
2. `BackendTurnSession` 直接读取 reducer state
3. 删掉 legacy progress dict 桥接

关闭信号：

- `runtime/live.py` 不再承担主状态推进职责
- 当前状态：
  - 已新增 `src/openrelay/presentation/live_turn.py`，提供 `LiveTurnPresenter`
  - `src/openrelay/runtime/turn.py` 在拿到 reducer state 时，已优先通过 presenter 把 `LiveTurnViewModel` 投影为 streaming snapshot
  - `src/openrelay/runtime/interactions/controller.py` 已去掉 `emit_progress` 回调；runtime approval 展示现在只走 `ApprovalRequestedEvent/ApprovalResolvedEvent + presenter`，不再回落到 `interaction.requested/resolved -> apply_live_progress(...)` 兼容桥
  - spinner 与 `runtime/live.py` 内的 `apply_live_progress(...)` 仍保留给 legacy/兼容测试路径，因此阶段 3 目前完成了“runtime 主路径脱离 legacy progress bridge”，但还没完成 compatibility live state machine 的最终清理

### 阶段 4：移除 legacy backend 主路径

目标：

- 让 orchestrator 只保留 runtime backend

步骤：

1. 去掉 Codex 的旧 `Backend.run` 主路径
2. 删除 `src/openrelay/backends/codex.py`
3. 收敛 registry / orchestrator

关闭信号：

- runtime turn 完全不再依赖 legacy `Backend`

### 阶段 5：补 Claude 同构 adapter

目标：

- 强制第二个 backend 也通过同一模型接入

步骤：

1. 建立 `claude_adapter/` 目录
2. 提供最小 `AgentBackend` 实现
3. 接到 orchestrator / registry

关闭信号：

- 第二个 backend 可以不走 legacy path 运行

## 完成判定

当以下条件全部满足时，`OR-TASK-001` 才可以关闭：

- `docs/design/agent-runtime-relay.md` 仍是唯一主设计文档
- 本文列出的结构性收敛已经完成，而不是只新增并行层
- Feishu / presentation / interaction 不再直接暴露 provider method / item type
- `src/openrelay/backends/codex.py` 已被删除
- Claude 至少以同构 adapter 占位接入
- runtime 主路径只剩：
  - `AgentRuntimeService`
  - `AgentBackend`
  - `RuntimeEvent`
  - `LiveTurnViewModel`
  - `LiveTurnPresenter`

## 本轮证据

- 本文：`docs/design/agent-runtime-relay-implementation-plan.md`
- 主设计文档：`docs/design/agent-runtime-relay.md`
- 任务板：`docs/design/TaskBoard.md`
- `src/openrelay/backends/codex_adapter/transport.py` 已新增 `CodexRpcTransport`，把 app-server client 生命周期、request、notification 分发和 server request 分发收敛为独立 transport 层。
- `src/openrelay/backends/codex_adapter/client.py` 已新增 `CodexSessionClient`，承接 session list/read/compact、thread start/resume 和 turn 启动逻辑。
- `src/openrelay/backends/codex_adapter/turn_stream.py` 已新增 `CodexTurnStream`，把 turn 生命周期、终态 future 和 pending approval 移出 `CodexRuntimeBackend`。
- `src/openrelay/backends/codex_adapter/mapper.py` 已新增 `CodexTurnState`，并把 `agent_text_by_id`、reasoning 聚合、tool output 聚合、`usage`、`final_text` 等 turn 内状态移出 mapper 实例。
- `tests/test_codex_protocol_mapper.py`、`tests/test_codex_runtime_backend.py` 已迁移到新结构；`tests/test_runtime.py`、`tests/test_agent_runtime.py` 回归通过，说明 adapter 内部拆层未改变 runtime 主路径外部行为。
- `src/openrelay/backends/codex_adapter/mapper.py` 现已把审批所需的统一字段下沉到 `ApprovalRequest.payload`，包括 `command`、`cwd`、`reason`、`permissions`、`questions`、`requested_schema` 等，interaction 层不再需要从 `provider_payload.method` 反推语义。
- `src/openrelay/runtime/interactions/controller.py` 已新增 `request_approval(...)`，并按 `ApprovalRequest.kind` + 统一 payload 处理 command / file_change / permissions / user_input 四类审批。
- `src/openrelay/runtime/turn.py` 的 runtime approval 分支现已直接消费 `ApprovalRequest` 和 `ApprovalDecision`，删掉了 turn 层本地的 provider-response -> decision 翻译逻辑。
- 已新增 `tests/test_runtime_interactions.py`，验证在 `provider_payload={}` 的情况下，`RunInteractionController.request_approval(...)` 仍能完成 command approval 交互，说明 runtime 主路径已不再依赖 provider method 作为审批入口。
- `src/openrelay/presentation/live_turn.py` 已新增 `LiveTurnPresenter`，开始负责 `LiveTurnViewModel -> snapshot/process_text/final_reply` 投影，不再要求 `turn.py` 自己理解 assistant / reasoning / tool / approval 的展示组合。
- `src/openrelay/runtime/orchestrator.py` 已装配 `LiveTurnPresenter`；`src/openrelay/runtime/turn.py` 在 runtime event 到达后，如果 reducer state 已可读，则优先直接用 presenter 基于 `LiveTurnViewModel` 重建 snapshot，只在缺少 state 的过渡时刻才回退到 `apply_runtime_event(...)`。
- 已新增 `tests/test_live_turn_presenter.py`，验证 presenter 能从统一 `LiveTurnViewModel` 直接生成包含 reasoning / command / approval / plan 的 process panel 文本，说明阶段 3 已开始从“事件桥接”转向“状态投影”。
- `src/openrelay/runtime/turn.py` 现已进一步移除普通 runtime event 对 `apply_runtime_event(...)` 的依赖；除 `SessionStartedEvent` 的 native session 同步和 approval resolved 的过渡提示外，runtime 展示更新已优先收敛到 “registry state -> presenter snapshot” 主路径。
- `src/openrelay/presentation/live_turn.py` 已新增 approval resolved 过渡态投影；`src/openrelay/runtime/turn.py` 不再通过 `apply_live_progress(...)` 手工补 `interaction.resolved`，而是直接让 presenter 更新 snapshot，进一步缩小 legacy progress bridge 的剩余范围。
- `src/openrelay/runtime/turn.py` 已移除 runtime 主路径中的 `run.started` 进度注入和未使用的 `on_partial_text(...)` 直写逻辑；assistant partial 现在完全依赖 reducer state + presenter snapshot 投影，legacy live-state 直接写入点继续减少。
- `src/openrelay/presentation/live_turn.py` 现已接管 `native_session_id` 同步和 spinner 帧推进的 snapshot 变换；`src/openrelay/runtime/turn.py` 不再直接写 `live_state[\"native_session_id\"]` 或 `live_state[\"spinner_frame\"]`，剩余的 live-state 管理已基本集中到 presenter。
- `src/openrelay/runtime/live.py` 已删除无调用的 `apply_runtime_event(...)` 桥接函数，并把 `create_live_reply_state(...)`、`build_reply_card(...)` 收敛为委托 `LiveTurnPresenter` 的兼容入口；当前文件主要只剩 `apply_live_progress(...)` 和 process panel / reply card 格式化兼容逻辑。
- `src/openrelay/runtime/interactions/controller.py` 现已删除 runtime 主路径不再需要的 `emit_progress` 依赖；`src/openrelay/runtime/turn.py` 也已去掉 `on_progress(...) -> apply_live_progress(...)` 入口，说明 approval 交互展示已完全切到统一 runtime event + presenter 投影。
- `src/openrelay/presentation/live_turn.py` 已补充对已 resolved approval interaction 的保留逻辑；即使 reducer state 在 `approval.resolved` 后清空 `pending_approval`，streaming snapshot 仍能稳定显示 “Resuming / Approval accepted” 这一过渡结果，而不必再借助 legacy progress event 维持 UI。
