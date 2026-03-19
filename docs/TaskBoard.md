# Design Task Board

更新时间：2026-03-19

## Landed

- [x] OR-TASK-007 消息行为日志与可观测性收敛
  - **目标**：为 Feishu 入站消息到最终回复建立一条可持久化、可查询、可回放的结构化消息行为日志链路，替代当前零散文本日志 + 内存态 runtime event 的弱观测方式。
  - **完成情况**：`observability/` 独立边界、SQLite `message_event_log` schema、`MessageTraceRecorder` / 查询服务、主路径最小埋点和仓库内 trace CLI 均已落地；现在已能稳定记录 ingress、session resolve、turn terminal、storage session saved、reply sent / failed 与队列补充输入等关键事件，并支持按 message / session / trace / turn 读取时间线。
  - **落地证据**：
    - `docs/design/or-task-007-message-observability-design.md`
    - `docs/design/or-task-007-message-observability-detailed-design.md`
    - `src/openrelay/observability/__init__.py`
    - `src/openrelay/observability/models.py`
    - `src/openrelay/observability/context.py`
    - `src/openrelay/observability/store.py`
    - `src/openrelay/observability/recorder.py`
    - `src/openrelay/observability/query.py`
    - `src/openrelay/runtime/message_application.py`
    - `src/openrelay/runtime/reply_service.py`
    - `src/openrelay/runtime/turn.py`
    - `src/openrelay/runtime/turn_application.py`
    - `src/openrelay/runtime/turn_execution.py`
    - `src/openrelay/runtime/turn_run_controller.py`
    - `src/openrelay/runtime/turn_runtime_event_bridge.py`
    - `src/openrelay/storage/state.py`
    - `src/openrelay/tools/trace.py`
    - `pyproject.toml`
  - **验证证据**：
    - `uv run pytest tests/storage/test_message_observability.py tests/runtime/test_message_observability.py tests/runtime/test_turn.py tests/storage/test_state_store.py`

- [x] OR-TASK-009 架构重构总体设计与分阶段实施收敛
  - **目标**：从模块职责划分和长期演化角度，为下一轮架构重构固定总体边界、事实来源、依赖方向和分阶段实施顺序。
  - **完成情况**：总体设计稿、详细设计稿、端到端执行蓝图与多轮端到端代码重构已落地；storage/session repository 边界、command parser/registry/handler 拆分、消息入口 application service、runtime reply service、turn execution service、typed live turn view model 与 Feishu renderer 分层，以及 orchestrator 装配根化均已进入主路径。
  - **落地证据**：
    - `docs/design/or-task-009-architecture-refactor-overall-design.md`
    - `docs/design/or-task-009-architecture-refactor-detailed-design.md`
    - `docs/design/or-task-009-end-to-end-refactor-blueprint.md`
    - `src/openrelay/storage/db.py`
    - `src/openrelay/storage/repositories.py`
    - `src/openrelay/session/repositories.py`
    - `src/openrelay/session/defaults.py`
    - `src/openrelay/runtime/message_dispatch.py`
    - `src/openrelay/runtime/message_application.py`
    - `src/openrelay/runtime/command_router.py`
    - `src/openrelay/runtime/turn_application.py`
    - `src/openrelay/runtime/turn_run_controller.py`
    - `src/openrelay/runtime/turn_runtime_event_bridge.py`
    - `src/openrelay/runtime/reply_service.py`
    - `src/openrelay/runtime/turn_execution.py`
    - `src/openrelay/presentation/models.py`
    - `src/openrelay/presentation/live_turn_view_builder.py`
    - `src/openrelay/feishu/renderers/live_turn_renderer.py`
    - `src/openrelay/runtime/orchestrator.py`
  - **验证证据**：
    - `uv run pytest`

- [x] OR-TASK-008 工作区目录选择卡收敛
  - **目标**：把工作区切换从 `/cwd`、`/cd` 的命令式输入收敛成面向飞书用户的工作区目录选择卡，在单一根目录内支持逐级浏览、返回、搜索和分页。
  - **完成情况**：正式设计稿已补齐；`/workspace` 已成为主入口；工作区卡已支持 `~` 根别名、默认 `~/Projects`、逐级浏览、返回上一级、回到根目录、搜索、隐藏目录显式开关、分页和选择当前目录；`/cwd`、`/cd` 已从 README、帮助文案和主面板入口中退出用户主路径。
  - **落地证据**：
    - `docs/archived/or-task-008-workspace-picker-design.md`
    - `README.md`
    - `src/openrelay/session/workspace.py`
    - `src/openrelay/presentation/panel.py`
    - `src/openrelay/runtime/command_router.py`
    - `src/openrelay/runtime/command_handlers/workspace.py`
    - `src/openrelay/runtime/help.py`
    - `tests/test_session_workspace.py`
    - `tests/test_runtime_commands.py`
    - `tests/test_session_list_card.py`
  - **后续 follow-up**：
    - 最近使用目录 / 固定目录能力另开任务，不再继续挂在本任务下。
    - `/shortcut` 的卡片化维护另开任务，不和工作区主路径收敛混在一起。

- [x] OR-TASK-006 Codex TUI 与飞书端体验差距调研与首轮 transcript 富文本渲染
  - **目标**：从飞书用户体验而不是 TUI 命令面对齐出发，判断哪些 Codex 能力值得迁移、哪些能力应明确不纳入飞书场景，并先收敛 transcript 主路径里最直接影响可读性的富文本渲染问题。
  - **完成情况**：UX 视角调研稿已完成；飞书 transcript card 的首轮 Codex 风格富文本渲染已进入主路径，包括命令/输出高亮、git diff 红绿标签与彩色文本、Rich spans 命令高亮链路、shell-aware 命令换行、命令中字面换行的树前缀保真、正文内联代码自定义颜色渲染，以及 `turn/diff/updated` 直接消费协议 `diff` 正文的兜底展示；后续未完成部分已拆为独立体验任务，不再继续挂在调研任务里。
  - **落地证据**：
    - `docs/archived/or-task-006-feishu-vs-codex-tui-gap-analysis.md`
    - `docs/archived/or-task-006-rich-command-highlighting-design.md`
    - `src/openrelay/feishu/highlight.py`
    - `src/openrelay/feishu/reply_card.py`
    - `tests/test_feishu_streaming.py`
    - `tests/test_runtime_rendering.py`
  - **后续 follow-up**：
    - “等待用户处理”的统一交互单列任务推进。
    - “当前会话状态与控制入口”单列任务推进。
    - “异步回看”单列任务推进。

- [x] OR-TASK-005 Runtime / Session / Presentation 边界收敛设计
  - **目标**：基于当时的实际代码结构而非既有文档，识别 runtime、session、storage、presentation 之间已经发生的职责漂移，并形成后续重构的正式设计稿。
  - **完成情况**：问题勘察稿、实施总纲和详细设计稿已完成；其后续实施内容已由 `OR-TASK-009` 吸收并落地，因此本任务作为“设计与问题收敛入口”关闭，不再保留为活跃执行任务。
  - **落地证据**：
    - `docs/archived/or-task-005-runtime-boundary-refactor-design.md`
    - `docs/archived/or-task-005-runtime-boundary-overall-plan.md`
    - `docs/archived/or-task-005-runtime-boundary-detailed-design.md`
    - `docs/design/or-task-009-architecture-refactor-overall-design.md`
    - `docs/design/or-task-009-architecture-refactor-detailed-design.md`
    - `docs/design/or-task-009-end-to-end-refactor-blueprint.md`
  - **后续 follow-up**：
    - 后续若再出现边界漂移，应直接以新的架构任务进入任务板，而不是回到 `005-A` ~ `005-D` 的旧拆分。

## Active

### [ ] OR-TASK-010 等待用户处理统一交互
- **目标**：把 terminal interaction、user input、MCP elicitation 等“系统在等用户继续”的场景统一成同一种飞书交互模型，让用户能清楚知道在等什么、该如何回复、提交后发生什么。
- **当前关注**：现在不同等待态仍按底层事件类型分散处理；用户能看到卡住，但还不能始终自然地接住输入、选择和确认。
- **关闭条件**：
  - 完成正式设计稿，明确等待态分类、统一卡片语义、输入/选择/确认控件边界和不做项。
  - 主路径代码能把至少 terminal interaction、user input、MCP elicitation 三类事件收敛到统一回复入口。
  - 用户提交后能收到稳定的“已发送/继续处理中”反馈，并且线程内能识别当前等待态是否已结束。
- **建议产物 / 已完成证据**：
  - `docs/design/`
  - `src/openrelay/runtime/`
  - `src/openrelay/feishu/`
- **后续 follow-up**：
  - 若后续需要更复杂表单或多步确认，再单独拆产品任务，不在第一轮统一交互里提前透支复杂度。

### [ ] OR-TASK-011 当前会话状态与控制入口收敛
- **目标**：围绕“当前这条会话正在做什么、停在哪里、下一步能做什么”收敛一个稳定入口，把高频控制动作从分散命令和零散卡片中拉回到同一上下文。
- **当前关注**：停止、状态查看、继续等待态、压缩上下文等动作虽然基本可用，但入口仍分散；飞书线程里缺少足够稳定的“当前会话控制面”。
- **关闭条件**：
  - 完成正式设计稿，明确当前会话状态模型、控制入口位置、高频动作集合和低频动作下沉策略。
  - 代码主路径里至少提供停止、查看状态、继续等待态、压缩上下文四类高频动作的集中入口。
  - 飞书端可稳定区分运行中、等待用户、已完成、失败、已停止等核心状态。
- **建议产物 / 已完成证据**：
  - `docs/design/`
  - `src/openrelay/presentation/`
  - `src/openrelay/feishu/`
  - `src/openrelay/runtime/`
- **后续 follow-up**：
  - 低频运行选项若需要暴露，优先作为二级入口，而不是继续把主入口做成控制台。

### [ ] OR-TASK-012 飞书异步回看体验收敛
- **目标**：把“过一段时间回来快速看懂发生了什么”做成飞书端的一等体验，让用户无需通读整段 transcript 也能恢复上下文并继续推进。
- **当前关注**：transcript 富文本渲染已经明显提升可读性，但异步回看仍缺少稳定摘要、停止原因、下一步建议和历史会话快速预览。
- **关闭条件**：
  - 完成正式设计稿，明确异步回看的状态摘要、关键动作摘要、停止原因、下一步建议和历史恢复入口。
  - transcript 或相关卡片能稳定提供“发生了什么/为什么停下/建议下一步”的最小摘要闭环。
  - 历史会话列表或恢复入口能支持快速判断“要不要继续这条线”。
- **建议产物 / 已完成证据**：
  - `docs/design/`
  - `src/openrelay/presentation/`
  - `src/openrelay/feishu/`
  - `src/openrelay/runtime/panel_service.py`
- **后续 follow-up**：
  - 如果后续需要更强的事件时间线或审计视图，应和 `OR-TASK-007` 的 observability 能力联动，不重复建设两套事实来源。

### [ ] OR-TASK-013 工作区快捷入口与目录维护体验收敛
- **目标**：在 `OR-TASK-008` 已完成工作区主路径收敛的基础上，继续降低频繁切目录的成本，把最近使用目录、固定目录和快捷目录维护收敛成更自然的飞书体验。
- **当前关注**：当前工作区浏览已经可用，但高频目录跳转仍依赖逐级点击或 `/shortcut` 子命令；常用目录入口还没有形成稳定的一等体验。
- **关闭条件**：
  - 完成正式设计稿，明确最近使用目录、固定目录、快捷目录三者的关系、优先级和展示边界。
  - 工作区卡或相关入口能稳定展示高频目录快捷入口，减少重复逐级浏览。
  - `/shortcut` 的增删改至少有一条不依赖纯命令记忆的卡片化维护路径。
- **建议产物 / 已完成证据**：
  - `docs/design/`
  - `src/openrelay/session/workspace.py`
  - `src/openrelay/session/shortcuts.py`
  - `src/openrelay/presentation/panel.py`
  - `src/openrelay/runtime/command_handlers/shortcut.py`
- **后续 follow-up**：
  - 若后续需要跨用户共享目录模板，应另开任务，不把团队级目录治理提前塞进当前个人工作区体验里。

## 使用约定

- 新的设计 / 架构 / 体验类任务，应直接新增新的 `OR-TASK-xxx` 条目，不回退到已关闭任务下追加“待完成”。
- 只有关闭条件全部满足、且证据已在同一轮改动中回写到仓库时，才把任务主复选框改成已完成。
- 后续新增条目继续遵循 `docs/task-board-protocol.md`。
