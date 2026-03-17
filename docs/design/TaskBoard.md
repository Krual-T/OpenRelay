# Design Task Board

更新时间：2026-03-18

## Landed

- 当前无保留的已落地任务；历史已完成条目已从任务板移除。

## Active

### [ ] OR-TASK-006 Codex TUI 与飞书端体验差距收敛
- **目标**：基于本机 `codex-cli 0.115.0` 与当前 `openrelay` 主线路径，明确飞书端离“接近 Codex TUI 原生体验”还缺哪些关键交互，并把后续实现拆成可执行优先级。
- **当前状态**：差距调研稿已完成，当前任务剩余的是把 `P0 / P1 / P2` 建议继续拆成具体实现任务。
- **待完成**：
  - 把 `terminal.interaction`、`user_input`、`fork` 等建议拆成独立实现子任务并逐步落地。
- **已完成证据**：
  - `docs/design/or-task-006-feishu-vs-codex-tui-gap-analysis.md`
- **后续 follow-up**：
  - 优先把 `terminal.interaction` 与 `user_input` 拆成独立实现任务，避免“命令面、卡片样式、runtime contract”混成一个大 patch。
  - 在开始实现前，先决定 `fork` 是走 external app-server 正式能力，还是先作为 blocker 留在能力映射表中。

### [ ] OR-TASK-005 Runtime / Session / Presentation 边界收敛设计
- **目标**：基于当前实际代码结构而非既有文档，识别 runtime、session、storage、presentation 之间已经发生的职责漂移，并形成后续重构的正式设计稿。
- **当前状态**：设计稿已完成，当前任务只剩进入实现阶段后的子任务拆分与落地。
- **待完成**：
  - 把设计稿拆成可执行子任务并逐步落地。
- **已完成证据**：
  - `docs/design/or-task-005-runtime-boundary-refactor-design.md`
- **后续 follow-up**：
  - 优先拆出 session/storage repository 边界，再处理 orchestrator 与命令层拆分。
  - 在实现阶段单独建立子任务，避免把 storage、runtime、Feishu 渲染三条线混成一个大 patch。

## 使用约定

- 当前设计主线任务已全部落地；若再开启新任务，请直接新增新的 `OR-TASK-xxx` 条目。
- 后续若再开启新的设计主线，新增条目应继续遵循 `docs/design/task-board-protocol.md`。
