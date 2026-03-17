# Design Task Board

更新时间：2026-03-18

## Landed

- 当前无保留的已落地任务；历史已完成条目已从任务板移除。

## Active

### [ ] OR-TASK-006 Codex TUI 与飞书端体验差距收敛
- **目标**：以飞书用户体验而不是 TUI 命令面对齐为主，判断哪些 Codex 能力值得迁移，哪些能力应明确不纳入飞书场景，并据此收敛真正的高优先级体验问题。
- **当前状态**：调研稿已重写为 UX 视角；当前任务剩余的是把“等待用户处理的统一交互”“当前会话状态与控制入口”“异步回看”拆成后续设计或实现任务。
- **待完成**：
  - 把“等待用户处理”的统一交互体验拆成独立任务。
  - 把“当前会话控制入口”和“异步回看”拆成独立任务。
  - 明确记录哪些 Codex CLI 能力在飞书场景下属于刻意不支持，而不是残缺未补。
- **已完成证据**：
  - `docs/design/or-task-006-feishu-vs-codex-tui-gap-analysis.md`
- **后续 follow-up**：
  - 优先把 terminal interaction、user input、MCP elicitation 从用户视角收敛成统一“等待用户处理”模型，再讨论底层事件差异。
  - 对 `fork`、`login`、`logout`、`cloud`、`features` 等能力先做产品取舍，不默认进入实现队列。

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
