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
  - 首页已弱化 `main/develop` 这类实现细节，改为强调“按目录承接不同项目的 Codex 定义、skills 与能力边界”这一真实优势，并补充与 OpenClaw 风格方案的取舍对比。
  - 首页已去掉对 webhook 的宣传，改为强调飞书长连接主路径，以及“不同目录承接不同 agent 能力、可插拔 skills 与飞书文档相关集成”这类真实使用场景。
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

### [x] OR-TASK-002 Codex App-Server Typed Contract 收敛
- **目标**：把 `openrelay` 的 Codex app-server 适配基线收敛到官方 `codex >= 0.115.0` external typed contract，明确 render / system / ignore / observe 分类，并用单一语义层承接 typed 事件。
- **结果**：
  - Codex 适配主线已经收敛到 typed-only external contract，不再保留 external `codex/event/*` 正式兼容路径。
  - `app_server.py` 已退回到底层 transport / RPC 客户端职责，不再维护旧版 turn 消费主路径。
  - typed 事件注册、语义映射、运行时投影已经形成清晰分层，unknown event 会统一进入 observe notice，而不是静默丢失。
  - `thread/status/changed`、`skills/changed`、`turn/diff/updated`、`account/rateLimits/updated` 等 typed system 事件已进入 runtime state。
  - 设计文档已改写为面向 typed-only 基线的正式说明，不再把 `v1 / v2` 双轨当作持续设计目标。
- **主要证据**：
  - `src/openrelay/backends/codex_adapter/event_registry.py`
  - `src/openrelay/backends/codex_adapter/mapper.py`
  - `src/openrelay/backends/codex_adapter/semantic_mapper.py`
  - `src/openrelay/backends/codex_adapter/runtime_projector.py`
  - `src/openrelay/backends/codex_adapter/app_server.py`
  - `src/openrelay/agent_runtime/reducer.py`
  - `docs/design/codex-app-server-event-consumption-plan.md`
  - `docs/design/codex-app-server-event-consumption-detailed-design.md`
  - `tests/test_codex_protocol_mapper.py`
  - `tests/test_codex_runtime_backend.py`
  - `tests/test_agent_runtime.py`
  - 本机额外 probe 已再次确认：当前外部 typed 样本未出现 unknown method；新增观察到 `thread/started`、`item/reasoning/summaryPartAdded`、`item/reasoning/summaryTextDelta`

## Active

### [ ] OR-TASK-003 Feishu 流式回复收敛为 TUI Transcript 投影
- **目标**：把飞书当前“过程面板 + 最终答案”的双区渲染，收敛为与 Codex TUI 更一致的单条 transcript 投影，使执行记录、解释文字和 follow-up 建议能在线性正文里自然混排。
- **当前关注**：
  - 明确 transcript 渲染 contract 应该落在哪一层，避免把 provider 事件细节直接泄漏到飞书卡片。
  - 明确 streaming 阶段与 final 阶段是否共用同一份 transcript builder，消除当前双套拼装逻辑。
  - 写死 transcript-first 约束：目标是 append-only / tail-replace 的 transcript block 历史，而不是把最新状态快照重新渲染得像 transcript。
  - 明确 `plan.updated` 在飞书里的语义应保留历史痕迹，不能继续只表现为“当前 Plan 板块”。
  - 明确 `rate_limits`、`thread_status`、`available_skills`、`last_diff_id` 这类 runtime 元信息默认不进入主 transcript。
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
  - 2026-03-17 已补充 transcript contract、plan 历史语义与非正文 runtime 元信息过滤原则。
- **后续 follow-up**：
  - 按设计引入统一 transcript builder，并删除流式 / 最终态的重复拼装。
  - 决定 `plan` 是 append-only 还是仅允许覆盖 transcript 尾部最后一个 live block，并把规则下沉到 presenter / reducer contract。
  - 决定是否保留可配置的 compact card 模式，避免一次性把旧展示能力彻底删死。

## 使用约定

- 当前打开的设计主线任务见 `OR-TASK-003`；`OR-TASK-002` 已落地。
- 后续若再开启新的设计主线，新增条目应继续遵循 `docs/design/task-board-protocol.md`。
