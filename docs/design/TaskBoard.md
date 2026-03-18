# Design Task Board

更新时间：2026-03-18

## Landed

- 当前无保留的已落地任务；历史已完成条目已从任务板移除。

## Active

### [ ] OR-TASK-008 工作区目录选择卡收敛
- **目标**：把工作区切换从 `/cwd`、`/cd` 的命令式输入收敛成面向飞书用户的工作区目录选择卡，在单一根目录内支持逐级浏览、返回、搜索和分页。
- **当前状态**：设计稿已补齐并按用户反馈进入第二阶段；代码已支持 `/workspace` 主入口、`~` 根别名、默认 `~/Projects`、逐级浏览、返回上一级、搜索输入框、隐藏目录显式开关和 `/resume` 风格分页；剩余工作主要是继续打磨视觉样式和快捷目录维护体验。
- **关闭条件**：
  - 完成正式设计稿，明确根目录别名、逐级浏览边界、交互容器语义、搜索与分页策略和不做项。
  - 代码主路径不再依赖 `/cwd`、`/cd` 作为用户入口。
  - 工作区选择卡可稳定进行目录浏览、目录搜索、返回上一级和选择当前目录。
- **已完成证据**：
  - `docs/design/or-task-008-workspace-picker-design.md`
  - `src/openrelay/session/workspace.py`
  - `src/openrelay/presentation/panel.py`
  - `src/openrelay/runtime/commands.py`
- **后续 follow-up**：
  - 补“最近使用目录 / 固定目录”分组，降低逐级浏览成本。
  - 评估是否要把 `/shortcut` 的增删改也收敛到卡片里。

### [ ] OR-TASK-007 消息行为日志与可观测性收敛
- **目标**：为 Feishu 入站消息到最终回复建立一条可持久化、可查询、可回放的结构化消息行为日志链路，替代当前零散文本日志 + 内存态 runtime event 的弱观测方式。
- **当前状态**：总体设计和详细设计均已完成；当前进入第一阶段实现准备，下一步应落 `observability/` 包、SQLite schema 和主路径最小埋点。
- **关闭条件**：
  - 完成正式设计稿，明确事件模型、关联键、埋点位置、SQLite schema、保留策略与分阶段实施路径。
  - 在代码中落地最小闭环：至少能记录 ingress、session resolve、turn terminal、reply sent 等主路径事件。
  - 提供一个仓库内可用的 trace 读取入口，用于按 message / session / trace 查看时间线。
- **已完成证据**：
  - `docs/design/or-task-007-message-observability-design.md`
  - `docs/design/or-task-007-message-observability-detailed-design.md`
- **后续 follow-up**：
  - 第一阶段优先实现 `MessageTraceRecorder` 与 `message_event_log`，不要先做 UI。
  - 高频 provider delta 先做聚合观测，不默认逐条入库。
  - observability 逻辑应独立成 store / recorder，不继续膨胀 `StateStore`。

### [ ] OR-TASK-006 Codex TUI 与飞书端体验差距收敛
- **目标**：以飞书用户体验而不是 TUI 命令面对齐为主，判断哪些 Codex 能力值得迁移，哪些能力应明确不纳入飞书场景，并据此收敛真正的高优先级体验问题。
- **当前状态**：调研稿已重写为 UX 视角；飞书 transcript card 已落首轮 Codex 风格命令/输出高亮，并继续把 git diff 收敛为“前缀红绿标签 + 行内容彩色文本”；streaming 路径已进一步收敛为“history 区变化整卡刷新，只有回答续写走增量更新”，避免 output / plan 区块出现打字机式追加；同时已把 `history_items[].type=summary` 与 `partial_text` 的语义拆开，前者只留在 transcript/history，后者只渲染 answer；这一轮又补上了基于 Rich spans 的命令高亮渲染链路、shell-aware 命令换行、命令中字面换行的树前缀保真，以及正文内联代码的自定义颜色渲染，并把 `turn/diff/updated` 的过时 `diffId` 适配修正为直接消费协议里的 `diff` 正文，作为 file change diff 展示兜底；当前任务剩余的是把“等待用户处理的统一交互”“当前会话状态与控制入口”“异步回看”拆成后续设计或实现任务。
- **待完成**：
  - 把“等待用户处理”的统一交互体验拆成独立任务。
  - 把“当前会话控制入口”和“异步回看”拆成独立任务。
  - 明确记录哪些 Codex CLI 能力在飞书场景下属于刻意不支持，而不是残缺未补。
- **已完成证据**：
  - `docs/design/or-task-006-feishu-vs-codex-tui-gap-analysis.md`
  - `docs/design/or-task-006-rich-command-highlighting-design.md`
  - `src/openrelay/feishu/highlight.py`
  - `src/openrelay/feishu/reply_card.py`
  - `tests/test_feishu_streaming.py`
- **后续 follow-up**：
  - 优先把 terminal interaction、user input、MCP elicitation 从用户视角收敛成统一“等待用户处理”模型，再讨论底层事件差异。
  - 对 `fork`、`login`、`logout`、`cloud`、`features` 等能力先做产品取舍，不默认进入实现队列。

### [ ] OR-TASK-005 Runtime / Session / Presentation 边界收敛设计
- **目标**：基于当前实际代码结构而非既有文档，识别 runtime、session、storage、presentation 之间已经发生的职责漂移，并形成后续重构的正式设计稿。
- **当前状态**：问题勘察稿、实施总纲、详细设计稿均已完成，当前任务进入按阶段实施与验证阶段。
- **待完成**：
  - 按详细设计方案拆出 `005-A` 到 `005-D` 并逐步落地。
- **已完成证据**：
  - `docs/design/or-task-005-runtime-boundary-refactor-design.md`
  - `docs/design/or-task-005-runtime-boundary-overall-plan.md`
  - `docs/design/or-task-005-runtime-boundary-detailed-design.md`
- **后续 follow-up**：
  - 优先拆出 session/storage repository 边界，再处理 orchestrator 与命令层拆分。
  - 在实现阶段单独建立子任务，避免把 storage、runtime、Feishu 渲染三条线混成一个大 patch。

### [ ] OR-TASK-009 架构重构总体设计与分阶段实施收敛
- **目标**：从模块职责划分和长期演化角度，为下一轮架构重构固定总体边界、事实来源、依赖方向和分阶段实施顺序。
- **当前状态**：总体设计稿、详细设计稿与端到端执行级蓝图均已完成；消息、session、command、turn 和 rendering 的主链路目标模块已按 Phase 1-5 排列，并形成可并行推进的实施入口。当前已落一轮 C 线实现：`BackendTurnSession` 已退化为 facade，turn 生命周期已拆到 `TurnApplicationService` / `TurnRunController` / `TurnRuntimeEventBridge`，同时补上 typed live turn view model builder 与 Feishu renderer 分层。
- **关闭条件**：
  - 完成正式总体设计稿，明确目标边界、事实来源、实施阶段和风险控制。
  - 任务板中记录对应设计证据和后续实施方向。
  - 后续详细设计或实施子任务具备可继续拆分的稳定入口。
- **已完成证据**：
  - `docs/design/or-task-009-architecture-refactor-overall-design.md`
  - `docs/design/or-task-009-architecture-refactor-detailed-design.md`
  - `docs/design/or-task-009-end-to-end-refactor-blueprint.md`
  - `src/openrelay/runtime/turn.py`
  - `src/openrelay/runtime/turn_application.py`
  - `src/openrelay/runtime/turn_run_controller.py`
  - `src/openrelay/runtime/turn_runtime_event_bridge.py`
  - `src/openrelay/presentation/live_turn_view_builder.py`
  - `src/openrelay/presentation/models.py`
  - `src/openrelay/feishu/renderers/live_turn_renderer.py`
- **后续 follow-up**：
  - 已形成端到端执行级设计，可按并行子任务推进 Phase 1-5 实施。
  - 主控接线仍需把 turn/rendering 新边界从 `runtime/orchestrator.py` 继续收敛到独立 application service。

## 使用约定

- 当前设计主线任务已全部落地；若再开启新任务，请直接新增新的 `OR-TASK-xxx` 条目。
- 后续若再开启新的设计主线，新增条目应继续遵循 `docs/design/task-board-protocol.md`。
