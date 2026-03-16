# Design Task Board

更新时间：2026-03-16

这份文档只保留当前唯一主线任务。

详细回写规则仍以 `docs/design/task-board-protocol.md` 为准，但任务板本身不再保留旧任务与历史设计分支。

## Ready

### [ ] OR-TASK-001 Agent Runtime Relay 主线收敛
- **优先级**：P0
- **目标**：把 `openrelay` 收敛为统一的 agent runtime relay，让 Feishu 壳层、runtime 主路径、session binding、interaction 和 presentation 都围绕 backend-neutral 的运行时语义组织，而不是继续围绕 Codex 专有协议长出结构。
- **当前关注**：
  - `openrelay` 仍有大量 runtime 语义直接继承自 Codex provider 形状。
  - backend adapter、runtime event、session binding、interaction、presentation 的边界还没有彻底按统一模型收口。
  - 未来 Claude Code 等 backend 的接入路径还没有被当前主结构自然吸收。
- **关闭条件**：
  - [ ] `docs/design/agent-runtime-relay.md` 继续作为唯一主线 design note，并保持和代码现状一致。
  - [ ] runtime 主层只依赖统一 agent runtime 模型，不再把 provider-specific method / item type 暴露为主路径语义。
  - [ ] backend adapter、session binding、interaction、presentation 的职责边界在实现上完成最小闭环。
  - [ ] 新增或调整的实现、测试和文档证据都回写到同一任务条目。
- **建议产物**：`docs/design/agent-runtime-relay.md`；`src/openrelay/` 下与 runtime、session、presentation、backend adapter 相关的后续实现与测试。
- **本轮新增证据**：
  - `docs/design/agent-runtime-relay.md` 已补充“实现补充附录”，明确第一阶段 Codex 事件映射、审批映射、binding 过渡、orchestrator 接线和测试矩阵。
  - 附录约束以当前仓库可验证实现为证据来源：`src/openrelay/backends/codex.py`、`src/openrelay/runtime/live.py`、`src/openrelay/runtime/interactions/controller.py`、`tests/test_codex_backend.py`。
  - 已新增 `src/openrelay/agent_runtime/` 下的统一 runtime model / event / backend contract / reducer / service 骨架，以及 `src/openrelay/session/models.py`、`src/openrelay/session/store.py` 的 binding store。
  - 已新增 `tests/test_agent_runtime.py`、`tests/test_session_binding_store.py`，并与 `tests/test_state.py`、`tests/test_session_scope.py` 一起验证通过，说明新骨架目前可与旧主路径并行存在。
  - 已新增 `src/openrelay/backends/codex_adapter/mapper.py` 与 `src/openrelay/backends/codex_adapter/__init__.py`，把 Codex app-server notification / server request 归约为统一 runtime event 与 `ApprovalRequest`，并内置 turn 归属、alias 去重、reasoning 聚合、tool 生命周期、usage 映射和审批响应构造。
  - 已新增 `tests/test_codex_protocol_mapper.py`，验证 `turn/started`、agent / reasoning alias 去重、reasoning summary 优先级、tool 生命周期、approval request / resolved、usage 和 turn 终态映射；并与既有 `tests/test_codex_backend.py`、`tests/test_agent_runtime.py` 一起通过。
  - 旧 `src/openrelay/backends/codex.py` 的 `CodexTurn.handle_notification(...)` 已切到消费 `CodexProtocolMapper` 输出的统一 runtime event，再翻译回现有 progress callback；现有 backend API、turn future 和交互回调保持兼容。
  - 已新增 `src/openrelay/backends/codex_adapter/backend.py`，提供 `AgentBackend` 版 `CodexRuntimeBackend`，直接复用现有 `CodexAppServerClient` 完成 session start / list / read / compact、runtime event sink 驱动的 turn 执行，以及 pending approval 的等待与决策回写。
  - `src/openrelay/agent_runtime/service.py` 的 `run_turn(...)` 已在 `TurnInput.metadata` 中补写 `relay_session_id`，使 backend adapter 能在不扩张接口的前提下产出带正确 relay session 归属的 runtime event。
  - 已新增 `tests/test_codex_runtime_backend.py`，验证 `CodexRuntimeBackend` 的 session 操作、runtime turn event 流和 approval resolve；并与 `tests/test_codex_backend.py`、`tests/test_codex_protocol_mapper.py`、`tests/test_agent_runtime.py`、`tests/test_session_binding_store.py` 一起通过。
  - `src/openrelay/runtime/orchestrator.py` 已在未显式覆盖 backend 的情况下初始化内建 `CodexRuntimeBackend` 和 `AgentRuntimeService`；`src/openrelay/runtime/turn.py` 的 `BackendTurnSession.run(...)` 对 Codex 路径已优先走 `AgentRuntimeService.run_turn(...)`，其他 backend 仍保留旧 `Backend.run(...)` 路径。
  - `BackendTurnSession` 已在 turn 级订阅 runtime event hub，把 `SessionStartedEvent`、assistant / reasoning / plan / tool / turn 终态重新投影为现有 live progress 事件，并在 `ApprovalRequestedEvent` 时复用现有 `RunInteractionController` 完成用户决策后回调 `AgentRuntimeService.resolve_approval(...)`。
  - 已补充 `tests/test_runtime.py` 中的 runtime-service 接线测试，验证 orchestrator 在显式注入 runtime backend 时会绕过旧 backend `run(...)` 并持久化新的 native session id；同时与现有 runtime/card-stream/interaction 回归一起通过。
  - `src/openrelay/runtime/commands.py` 的 `/resume`、`/compact` 原生 thread 操作已优先走 `AgentRuntimeService.list_sessions(...)`、`read_session(...)`、`compact_locator(...)`；旧 `CodexBackend.list_threads/read_thread/compact_thread` 只作为 fallback 保留。
  - `src/openrelay/runtime/panel_service.py` 的 `/resume` 会话卡片数据源已优先走 `AgentRuntimeService.list_sessions(...)`，使原生命令式恢复列表与新的 Codex runtime backend 共享同一 session 枚举入口。
  - 已补充 `tests/test_runtime.py` 中 runtime-service 驱动的 `/resume latest` 与 `/compact` 回归，验证在显式注入 runtime backend 时无需旧 backend 原生 thread 扩展方法也能完成会话恢复、thread 读取与 compact。
  - `src/openrelay/runtime/orchestrator.py` 现在对 backend 可用性的判断已基于“旧 backend 集合 + runtime backend 集合”的并集；`BackendTurnSession.run(...)` 也允许在只有 runtime backend、没有旧 `Backend` 实例时执行 Codex turn。
  - `/backend` 命令的可选 backend 校验已与 orchestrator 使用同一可用 backend 集合，不再要求 runtime-only backend 同时在旧 `backends` 映射里占位。
  - 已补充 `tests/test_runtime.py` 中 runtime-only 配置回归，验证在 `backends={}`、`runtime_backends={\"codex\": ...}` 的情况下仍能正常执行 Codex turn 并持久化 native session id。

## 使用约定

- 新工作默认都归入上面的唯一主线任务，不再新增平行 design task。
- 如果只完成部分收敛，不勾选主项，只更新关闭条件、证据和当前关注。
- 只有当主线关闭条件全部满足时，才允许把主复选框改成 `[x]`。
