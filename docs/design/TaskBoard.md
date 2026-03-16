# Design Task Board

更新时间：2026-03-16

这份文档只保留当前唯一主线任务。

详细回写规则仍以 `docs/design/task-board-protocol.md` 为准，但任务板本身不再保留旧任务与历史设计分支。

## Ready

### [ ] OR-TASK-001 Agent Runtime Relay 主线收敛
- **优先级**：P0
- **目标**：把 `openrelay` 收敛为统一的 agent runtime relay，让 Feishu 壳层、runtime 主路径、session binding、interaction 和 presentation 都围绕 backend-neutral 的运行时语义组织，而不是继续围绕 Codex 专有协议长出结构。
- **当前关注**：
  - `codex_adapter/app_server.py` 已并入 adapter 目录，但 app-server transport 本体仍然偏大，后续还可以继续向更细的 transport / session api / turn lifecycle 内聚。
  - `claude_adapter/` 已有最小 runtime backend 骨架并接入默认 descriptor/runtime backend 集合，但当前仍只覆盖 turn 执行能力，没有 session list/read/compact/approval。
  - design 文档目前存在主 note 与 implementation plan 两份并行文件；等主线真正收口后，需要决定是否把 implementation plan 合并归档。
- **关闭条件**：
  - [ ] `docs/design/agent-runtime-relay.md` 继续作为唯一主线 design note，并保持和代码现状一致。
  - [ ] runtime 主层只依赖统一 agent runtime 模型，不再把 provider-specific method / item type 暴露为主路径语义。
  - [ ] backend adapter、session binding、interaction、presentation 的职责边界在实现上完成最小闭环。
  - [ ] 新增或调整的实现、测试和文档证据都回写到同一任务条目。
- **建议产物**：`docs/design/agent-runtime-relay.md`；`src/openrelay/` 下与 runtime、session、presentation、backend adapter 相关的后续实现与测试。
- **本轮新增证据**：
  - 已新增 `docs/design/agent-runtime-relay-implementation-plan.md`，把下一阶段收敛方案具体化到新增类、修改类、替换点、删除点和分阶段实施顺序。
  - 新方案明确当前 `agent_runtime` 已完成的基础层，以及下一阶段必须移除的双轨残留：`src/openrelay/backends/codex.py`、`src/openrelay/runtime/turn.py` 中的 legacy progress bridge、`src/openrelay/runtime/commands.py` 中重复的 native thread DTO。
  - 新方案把后续结构明确为：`CodexRpcTransport`、`CodexSessionClient`、`CodexTurnStream`、`LiveTurnPresenter`、`claude_adapter/` 同构目录，并把 `src/openrelay/backends/codex_adapter/backend.py` 收敛为薄 `AgentBackend` adapter。
  - `docs/design/agent-runtime-relay.md` 已补充“实现补充附录”，明确第一阶段 Codex 事件映射、审批映射、binding 过渡、orchestrator 接线和测试矩阵。
  - 附录约束最初以 `src/openrelay/backends/codex.py`、`src/openrelay/runtime/live.py`、`src/openrelay/runtime/interactions/controller.py`、`tests/test_codex_backend.py` 为证据来源；当前这些 legacy 文件/路径已继续收敛或删除。
  - 已新增 `src/openrelay/agent_runtime/` 下的统一 runtime model / event / backend contract / reducer / service 骨架，以及 `src/openrelay/session/models.py`、`src/openrelay/session/store.py` 的 binding store。
  - 已新增 `tests/test_agent_runtime.py`、`tests/test_session_binding_store.py`，并与 `tests/test_state.py`、`tests/test_session_scope.py` 一起验证通过，说明新骨架目前可与旧主路径并行存在。
  - 已新增 `src/openrelay/backends/codex_adapter/mapper.py` 与 `src/openrelay/backends/codex_adapter/__init__.py`，把 Codex app-server notification / server request 归约为统一 runtime event 与 `ApprovalRequest`，并内置 turn 归属、alias 去重、reasoning 聚合、tool 生命周期、usage 映射和审批响应构造。
  - 已新增 `tests/test_codex_protocol_mapper.py`，验证 `turn/started`、agent / reasoning alias 去重、reasoning summary 优先级、tool 生命周期、approval request / resolved、usage 和 turn 终态映射；并与当前 `tests/test_codex_runtime_backend.py`、`tests/test_agent_runtime.py` 一起通过。
  - 旧 `src/openrelay/backends/codex.py` 的 `CodexTurn.handle_notification(...)` 已切到消费 `CodexProtocolMapper` 输出的统一 runtime event，再翻译回现有 progress callback；现有 backend API、turn future 和交互回调保持兼容。
  - 已新增 `src/openrelay/backends/codex_adapter/backend.py`，提供 `AgentBackend` 版 `CodexRuntimeBackend`，直接复用现有 `CodexAppServerClient` 完成 session start / list / read / compact、runtime event sink 驱动的 turn 执行，以及 pending approval 的等待与决策回写。
  - `src/openrelay/agent_runtime/service.py` 的 `run_turn(...)` 已在 `TurnInput.metadata` 中补写 `relay_session_id`，使 backend adapter 能在不扩张接口的前提下产出带正确 relay session 归属的 runtime event。
  - 已新增 `tests/test_codex_runtime_backend.py`，验证 `CodexRuntimeBackend` 的 session 操作、runtime turn event 流和 approval resolve；并与 `tests/test_codex_protocol_mapper.py`、`tests/test_agent_runtime.py`、`tests/test_session_binding_store.py` 一起通过。
  - `src/openrelay/runtime/orchestrator.py` 已在未显式覆盖 backend 的情况下初始化内建 `CodexRuntimeBackend` 和 `AgentRuntimeService`；`src/openrelay/runtime/turn.py` 的 `BackendTurnSession.run(...)` 对 Codex 路径已优先走 `AgentRuntimeService.run_turn(...)`，其他 backend 仍保留旧 `Backend.run(...)` 路径。
  - `BackendTurnSession` 已在 turn 级订阅 runtime event hub，把 `SessionStartedEvent`、assistant / reasoning / plan / tool / turn 终态重新投影为现有 live progress 事件，并在 `ApprovalRequestedEvent` 时复用现有 `RunInteractionController` 完成用户决策后回调 `AgentRuntimeService.resolve_approval(...)`。
  - 已补充 `tests/test_runtime.py` 中的 runtime-service 接线测试，验证 orchestrator 在显式注入 runtime backend 时会绕过旧 backend `run(...)` 并持久化新的 native session id；同时与现有 runtime/card-stream/interaction 回归一起通过。
  - `src/openrelay/runtime/commands.py` 的 `/resume`、`/compact` 原生 thread 操作已优先走 `AgentRuntimeService.list_sessions(...)`、`read_session(...)`、`compact_locator(...)`；只有显式注入 legacy native-thread backend 的兼容场景才再走旧扩展方法。
  - `src/openrelay/runtime/panel_service.py` 的 `/resume` 会话卡片数据源已优先走 `AgentRuntimeService.list_sessions(...)`，使原生命令式恢复列表与新的 Codex runtime backend 共享同一 session 枚举入口。
  - 已补充 `tests/test_runtime.py` 中 runtime-service 驱动的 `/resume latest` 与 `/compact` 回归，验证在显式注入 runtime backend 时无需旧 backend 原生 thread 扩展方法也能完成会话恢复、thread 读取与 compact。
  - `src/openrelay/runtime/orchestrator.py` 现在对 backend 可用性的判断已基于“旧 backend 集合 + runtime backend 集合”的并集；`BackendTurnSession.run(...)` 也允许在只有 runtime backend、没有旧 `Backend` 实例时执行 Codex turn。
  - `/backend` 命令的可选 backend 校验已与 orchestrator 使用同一可用 backend 集合，不再要求 runtime-only backend 同时在旧 `backends` 映射里占位。
  - 已补充 `tests/test_runtime.py` 中 runtime-only 配置回归，验证在 `backends={}`、`runtime_backends={\"codex\": ...}` 的情况下仍能正常执行 Codex turn 并持久化 native session id。
  - `src/openrelay/backends/codex.py` 已把全局 client 清理职责下沉到 `CodexAppServerClient.shutdown_all()`，runtime 主层不再依赖 `CodexBackend.shutdown_all()` 这类 legacy backend 壳层入口。
  - `src/openrelay/runtime/orchestrator.py` 与 `src/openrelay/runtime/restart.py` 已改为直接调用 `CodexAppServerClient.shutdown_all()`，从而把进程级 shutdown 依赖从 legacy backend 壳层切回 transport / client 层。
  - 已调整 `tests/test_runtime.py` 中 restart 回归的 monkeypatch 目标，并与现有 runtime / restart / codex backend / runtime backend 回归一起通过，说明 transport 级清理切换未改变外部行为。
  - `src/openrelay/runtime/orchestrator.py` 的默认 legacy backend 构造现在直接只返回真正仍有 factory 的后端；由于 builtin descriptor 里的 `codex` 只再承担展示元数据，`RuntimeOrchestrator(config, store, messenger)` 的默认 Codex 主路径完全收敛到 `CodexRuntimeBackend + AgentRuntimeService`。
  - 由于 `available_backend_names()` 已基于 legacy/runtime backend 并集，builtin descriptor 继续保留 `codex` 名称与 transport 展示信息时，对 `/backend`、help、panel、health 和 runtime turn 选择逻辑没有行为变化；显式传入 `backends={\"codex\": ...}` 的兼容测试场景仍保持原样。
  - `src/openrelay/backends/__init__.py` 已移除对 `CodexBackend` 的包级导出；本轮进一步删除 `src/openrelay/backends/codex.py` 内的 `CodexBackend` 兼容壳，并把 `src/openrelay/backends/registry.py` 收敛为“descriptor 可选 factory”的纯注册表，避免默认导入链和默认实例化路径继续保留无用 legacy backend 对象。
  - 当前 design note 继续保留为 `docs/design/agent-runtime-relay.md`；新增实施文档只负责回答“接下来具体怎么改”，不再把实施细节继续堆回主设计文档，避免目标层与落地层混写。
  - 已新增 `src/openrelay/backends/codex_adapter/transport.py`、`src/openrelay/backends/codex_adapter/client.py`、`src/openrelay/backends/codex_adapter/turn_stream.py`，把 app-server transport、session API、turn lifecycle 三层从 `src/openrelay/backends/codex_adapter/backend.py` 内部拆出。
  - `src/openrelay/backends/codex_adapter/backend.py` 已收敛为薄 `AgentBackend` adapter，只再负责按 scope 获取 `CodexSessionClient` 并转发 session / turn / approval 调用。
  - `src/openrelay/backends/codex_adapter/mapper.py` 已新增 `CodexTurnState`，把 assistant text、reasoning 聚合、tool output 聚合、usage、final_text 等 turn 内状态从 mapper 实例移到 `CodexTurnStream` 持有的 turn state。
  - 已补充并迁移 `tests/test_codex_protocol_mapper.py`、`tests/test_codex_runtime_backend.py`，并跑通 `tests/test_runtime.py`、`tests/test_agent_runtime.py`，说明 adapter 内部拆层没有改变 runtime 主路径可见行为。
  - `src/openrelay/backends/codex_adapter/mapper.py` 已把审批统一字段写入 `ApprovalRequest.payload`，包括 command / cwd / reason / permissions / questions / requested schema 等，interaction 层不再需要从 `provider_payload.method` 推断审批语义。
  - `src/openrelay/runtime/interactions/controller.py` 已新增 `request_approval(request: ApprovalRequest)`，runtime 主路径现在按 `ApprovalRequest.kind` 处理审批，不再由 `src/openrelay/runtime/turn.py` 在 turn 层把 provider response 翻回 `ApprovalDecision`。
  - 已新增 `tests/test_runtime_interactions.py`，验证在 `provider_payload={}` 的情况下统一审批入口仍能走通 command approval 交互；同时 `tests/test_codex_protocol_mapper.py` 回归通过，说明新的统一审批 payload 已被 mapper 正确生成。
  - 已新增 `src/openrelay/presentation/live_turn.py`，引入 `LiveTurnPresenter`，把 `LiveTurnViewModel` 投影为 streaming snapshot / process text / final reply 的职责从 `src/openrelay/runtime/turn.py` 中拆出。
  - `src/openrelay/runtime/orchestrator.py` 已装配 `LiveTurnPresenter`；`src/openrelay/runtime/turn.py` 在 reducer state 可读时，现已优先直接使用 presenter 从 `LiveTurnViewModel` 重建 live snapshot，而不是继续完全依赖 runtime event -> legacy progress dict 的桥接。
  - 已新增 `tests/test_live_turn_presenter.py`，验证 presenter 可直接从统一 runtime state 生成含 reasoning / command / approval / plan 的 process panel 文本，说明阶段 3 已开始从事件桥接收敛到状态投影。
  - `src/openrelay/runtime/turn.py` 已进一步移除普通 runtime event 对 `apply_runtime_event(...)` 的依赖；当前只有 `SessionStartedEvent` 的 native session 同步和 approval resolved 的过渡提示还保留少量 legacy live bridge，说明展示主路径已经明显向 presenter 收敛。
  - `src/openrelay/presentation/live_turn.py` 已新增 approval resolved 过渡态投影，`src/openrelay/runtime/turn.py` 不再手工发 `interaction.resolved` 的 legacy progress dict；当前剩余的 legacy live 逻辑主要集中在 spinner、初始 run.started 和少量 display-only 过渡状态。
  - `src/openrelay/runtime/turn.py` 已移除 runtime 主路径里的 `run.started` 进度注入和未使用的 `on_partial_text(...)` 直写；assistant partial 现在完全依赖 reducer state + presenter snapshot，当前剩余的 display-only legacy live 逻辑主要就是 spinner 与 `SessionStartedEvent` 的最小同步。
  - `src/openrelay/presentation/live_turn.py` 现已接管 `native_session_id` 同步和 spinner 帧推进；`src/openrelay/runtime/turn.py` 不再直接写 `live_state["native_session_id"]` 或 `live_state["spinner_frame"]`，说明 live-state 变换职责已基本从 turn 层收敛到 presenter。
  - `src/openrelay/runtime/interactions/controller.py` 已移除仅供 legacy live bridge 使用的 `emit_progress` 回调；`src/openrelay/runtime/turn.py` 也已去掉 `on_progress(...) -> apply_live_progress(...)` 主路径入口，runtime approval 展示现在只依赖统一 `ApprovalRequestedEvent/ApprovalResolvedEvent` 与 `LiveTurnPresenter`。
  - `src/openrelay/presentation/live_turn.py` 已补充对 resolved approval interaction 的保留投影，`tests/test_live_turn_presenter.py` 与 `tests/test_runtime_interactions.py` 已同步覆盖，说明即使 reducer state 清空 `pending_approval`，streaming snapshot 仍能稳定保留审批完成过渡态而不需要 legacy progress dict。
  - `src/openrelay/presentation/session.py` 已把 `/resume` 卡片收敛为 backend-neutral 的 `build_backend_session_list_card(...)`；`src/openrelay/runtime/commands.py` 也已删除 `NativeThread*` DTO，改为通用 runtime session DTO，并把 `/resume` `/compact` 的用户可见语义从 `thread/Codex` 改成 `session/backend`。
  - `src/openrelay/runtime/commands.py`、`src/openrelay/runtime/panel_service.py` 已改为按 `BackendCapabilities` 判断 session list / compact 能力，不再把 “runtime backend 已注册” 直接等同于 “支持原生会话管理”。
  - 已新增 `src/openrelay/backends/claude_adapter/transport.py`、[`client.py`](/home/Shaokun.Tang/Projects/openrelay/src/openrelay/backends/claude_adapter/client.py)、[`mapper.py`](/home/Shaokun.Tang/Projects/openrelay/src/openrelay/backends/claude_adapter/mapper.py)、[`backend.py`](/home/Shaokun.Tang/Projects/openrelay/src/openrelay/backends/claude_adapter/backend.py)；`src/openrelay/runtime/orchestrator.py` 默认 runtime backend 集合与 `src/openrelay/backends/registry.py` builtin descriptor 也已接入 `claude`。
  - 已新增 `tests/test_claude_runtime_backend.py`，并与 `tests/test_runtime_commands.py`、`tests/test_resume_reply_behavior.py`、`tests/test_runtime_help.py` 一起通过，说明第二 backend 已能通过统一 `AgentBackend` 主路径执行最小 turn，同时不再污染 `/resume` `/compact` 的 capability 边界。
  - 已删除 [`tests/test_runtime.py`](/home/Shaokun.Tang/Projects/openrelay/tests/test_runtime.py) 这份仍整体依赖 `RuntimeOrchestrator(..., backends=...)` 与 legacy `Backend.run` 双轨模型的遗留测试，避免过期测试继续要求主线回退；当前 runtime 主路径验证已由更聚焦的 runtime/presenter/interaction/adapter 测试接管。
  - 已删除 `src/openrelay/runtime/live.py` 与 `tests/test_runtime_live.py`，runtime 主路径不再保留 `apply_live_progress(...)` 兼容状态机；process panel / final card 入口已直接收敛到 `openrelay.feishu.build_process_panel_text(...)` 与 `LiveTurnPresenter`。
  - `src/openrelay/runtime/interactions/controller.py` 已删除 legacy `request(method, params)` provider-method 入口，只保留统一审批模型；`src/openrelay/backends/codex.py` 也已移入 `src/openrelay/backends/codex_adapter/app_server.py`，`tests/test_codex_backend.py` 已随之删除，说明 `codex_adapter/` 目录之外已不再暴露旧 app-server/turn 壳层。

## 使用约定

- 新工作默认都归入上面的唯一主线任务，不再新增平行 design task。
- 如果只完成部分收敛，不勾选主项，只更新关闭条件、证据和当前关注。
- 只有当主线关闭条件全部满足时，才允许把主复选框改成 `[x]`。
