# Design Task Board

更新时间：2026-03-16

## Landed

### [x] OR-TASK-001 Agent Runtime Relay 主线收敛
- **目标**：把 `openrelay` 收敛为统一的 agent runtime relay，让 Feishu 壳层、runtime 主路径、session binding、interaction 和 presentation 都围绕 backend-neutral 的运行时语义组织。
- **结果**：
  - `docs/design/agent-runtime-relay.md` 现为唯一主线 design note。
  - runtime 主层已收敛到统一 agent runtime 模型，不再把 provider-specific method / item type 暴露为主路径语义。
  - backend adapter、session binding、interaction、presentation 已形成最小闭环。
  - Codex 已收敛到 `src/openrelay/backends/codex_adapter/`，Claude 已以同构 `src/openrelay/backends/claude_adapter/` 占位接入。
  - legacy `src/openrelay/runtime/live.py`、legacy runtime orchestrator 测试、legacy codex backend 测试均已删除。
- **主要证据**：
  - `src/openrelay/agent_runtime/`
  - `src/openrelay/backends/codex_adapter/`
  - `src/openrelay/backends/claude_adapter/`
  - `src/openrelay/presentation/live_turn.py`
  - `src/openrelay/runtime/turn.py`
  - `src/openrelay/runtime/interactions/controller.py`
  - `tests/test_runtime_commands.py`
  - `tests/test_runtime_interactions.py`
  - `tests/test_live_turn_presenter.py`
  - `tests/test_codex_protocol_mapper.py`
  - `tests/test_codex_runtime_backend.py`
  - `tests/test_claude_runtime_backend.py`

## 使用约定

- 当前无打开的 design 主线任务。
- 后续若再开启新的设计主线，新增条目应继续遵循 `docs/design/task-board-protocol.md`。
