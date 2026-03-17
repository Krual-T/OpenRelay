# Design Task Board

更新时间：2026-03-17

## Landed

### [x] OR-TASK-004 README 首页重写与视觉入口收敛
- **目标**：把仓库首页重写成能直接说明 `openrelay` 产品定位、主路径能力和上手方式的 GitHub README，并把 `static/` 里的品牌图片纳入默认视觉入口。
- **结果**：
  - `README.md` 已从仓库内部说明文，收敛为面对 GitHub 访客的产品型首页。
  - 首页已使用 `static/openrelay_logo.png` 作为主视觉，强化项目识别度。
  - 首页已补齐项目定位、核心卖点、架构分层、快速开始、命令面与 backend 状态。
  - 文案已明确当前主线是 `Codex app-server`，`Claude` 仍是最小适配状态，避免宣传口径和真实能力脱节。
- **主要证据**：
  - `README.md`
  - `static/openrelay_logo.png`

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

### [ ] OR-TASK-002 Codex App-Server Typed Contract 收敛
- **目标**：把 `openrelay` 的 Codex app-server 适配基线收敛到官方 `codex >= 0.115.0` external typed contract，明确 render / system / ignore / observe 分类，并用单一语义层承接 typed 事件。
- **当前关注**：
  - 用真实 `0.115.x` app-server 流量确认 typed schema 实际事件面。
  - 补齐 `thread/status/changed`、`skills/changed`、`turn/diff/updated` 等 typed system 事件消费。
  - 收敛 external legacy `codex/event/*` 为 observe/debug，而不是正式兼容目标。
- **关闭条件**：
  - 设计文档明确 `codex >= 0.115.0` typed 基线与事件分类矩阵。
  - mapper 默认工作在 typed-only 模式。
  - external legacy 路径不再是正式输入面，剩余 observe/debug 边界被写清楚。
- **建议产物**：
  - `docs/design/codex-app-server-event-consumption-plan.md`
  - `docs/design/codex-app-server-event-consumption-detailed-design.md`
- **已完成证据**：
  - 本地日志已确认 `item/*` 与 `codex/event/*` 双轨并存。
  - 本地日志已确认 `codex/event/turn_aborted` 真实出现。
  - 官方 `0.115.0` external app-server transport 已停止发 `codex/event/*`。
  - 本机已升级到 `codex-cli 0.115.0` 并抓到真实 external typed 事件样本：
    `thread/status/changed`、`turn/started`、`item/started`、`item/completed`、`item/agentMessage/delta`、`thread/tokenUsage/updated`、`account/rateLimits/updated`、`turn/completed`
  - 设计文档已补齐 `codex >= 0.115.0` external typed contract 的全量消息矩阵，逐条写明作用、分类、当前状态与实测情况。
  - `docs/design/codex-app-server-consumption-comparison.md`
  - `docs/design/codex-app-server-event-consumption-plan.md`
  - `docs/design/codex-app-server-event-consumption-detailed-design.md`
- **后续 follow-up**：
  - 用本地 `codex 0.115.x` 抓真实 typed app-server schema，并对照 registry 做精简。
  - 把 typed system 事件真正接入上层状态，而不是只写入 snapshot。
  - 明确是否需要运行时版本检查，避免低版本 Codex 误接入。

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
