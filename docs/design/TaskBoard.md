# Design Task Board

更新时间：2026-03-17

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

## Active

### [ ] OR-TASK-002 Codex App-Server 双轨事件消费收敛
- **目标**：把 Codex app-server 的 v1 legacy 与 v2 typed 事件消费收敛为单一语义层，明确 render / system / ignore / fallback 分类，并消除同语义双消费。
- **当前关注**：
  - 明确哪些事件是 `v1 only`、哪些是 `v2 only`、哪些是双轨并存。
  - 设计统一的语义事件键与去重规则，尤其是 terminal event。
  - 收敛“必须渲染”“必须系统消费”“明确忽略”的分类表。
- **关闭条件**：
  - 设计文档明确事件分类矩阵与去重策略。
  - 配置策略明确是否保留 hybrid 默认。
  - mapper / turn stream 后续改造边界被写清楚。
- **建议产物**：
  - `docs/design/codex-app-server-event-consumption-plan.md`
- **已完成证据**：
  - 本地日志已确认 `item/*` 与 `codex/event/*` 双轨并存。
  - 本地日志已确认 `codex/event/turn_aborted` 真实出现。
  - `docs/design/codex-app-server-consumption-comparison.md`
  - `docs/design/codex-app-server-event-consumption-plan.md`
- **后续 follow-up**：
  - 按设计补齐 terminal legacy 兼容与 typed-only 系统事件消费。
  - 把 ignore 集合从“隐式未处理”改成“显式登记”。

### [ ] OR-TASK-003 Feishu 流式回复收敛为 TUI Transcript 投影
- **目标**：把飞书当前“过程面板 + 最终答案”的双区渲染，收敛为与 Codex TUI 更一致的单条 transcript 投影，使执行记录、解释文字和 follow-up 建议能在线性正文里自然混排。
- **当前关注**：
  - 明确 transcript 渲染 contract 应该落在哪一层，避免把 provider 事件细节直接泄漏到飞书卡片。
  - 明确 streaming 阶段与 final 阶段是否共用同一份 transcript builder，消除当前双套拼装逻辑。
  - 明确 `collapsible_panel`、`Execution Log` 和固定 `---` 分隔线如何退出主路径。
- **关闭条件**：
  - 设计文档明确现状链路、目标链路和迁移边界。
  - 需要改动的类、方法名、职责调整和替换顺序被写清楚。
  - 风险点、回退策略和最小验证方案被写清楚。
- **建议产物**：
  - `docs/design/feishu-tui-transcript-rendering-plan.md`
- **已完成证据**：
  - 当前实现入口：`src/openrelay/presentation/live_turn.py`
  - 当前实现入口：`src/openrelay/feishu/reply_card.py`
  - 当前实现入口：`src/openrelay/feishu/streaming.py`
  - `docs/design/feishu-tui-transcript-rendering-plan.md`
- **后续 follow-up**：
  - 按设计引入统一 transcript builder，并删除流式 / 最终态的重复拼装。
  - 决定是否保留可配置的 compact card 模式，避免一次性把旧展示能力彻底删死。

## 使用约定

- 当前打开的设计主线任务见 `OR-TASK-002`、`OR-TASK-003`。
- 后续若再开启新的设计主线，新增条目应继续遵循 `docs/design/task-board-protocol.md`。
