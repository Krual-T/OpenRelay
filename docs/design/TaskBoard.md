# Design Task Board

更新时间：2026-03-10

这份文档不再只是记录“开放问题”，而是作为 `openrelay` 当前设计与实现任务的任务板。

原则很简单：
- 一个条目就是一个可独立推进的任务，不再只停留在问题描述。
- 主复选框表示“这个任务已经可以关闭”；不是“已经讨论过”。
- 任务关闭前，优先补齐设计 note、实现边界、验证方式和后续 follow-up。
- Codex CLI 只能在满足关闭条件后自己勾选主复选框；详细规则见 `docs/design/task-board-protocol.md`。

## Ready

### [ ] OR-TASK-003 多机器人、多用户、多终端的支持方式
- **优先级**：P3
- **目标**：在保持会话隔离和可控性的前提下，让多机器人和多终端的使用方式足够清晰，不让用户搞不清楚“当前是谁在处理、在哪台机器上处理”。
- **当前关注**：一个进程是否管理多个机器人；不同用户是否拥有独立会话空间和工作目录；同一人跨电脑 / 终端如何 attach；会话归属按机器人、飞书用户、机器、终端还是 workspace 建模；多实例如何避免争抢会话；是否需要接管 / 迁移 / 释放 / 锁定机制。
- **关闭条件**：
  - [ ] 独立 design note 明确会话归属模型、实例竞争策略和接管规则。
  - [ ] 配置模型与状态存储模型收敛到一种清晰方案。
  - [ ] 至少一条最小实现路径落地，例如多实例锁、显式接管命令或 attach 语义。
  - [ ] 文档说明迁移、回滚和兼容边界。
- **建议产物**：`docs/design/` 下的专题 note；`src/openrelay/config.py`、`src/openrelay/state.py`、`src/openrelay/runtime.py` 等对应实现。

## Landed / Follow-up

### [x] OR-TASK-011 运行时职责边界设计收敛
- **当前状态**：本轮已落地。
- **已完成证据**：`docs/design/runtime-responsibility-boundary.md`、`src/openrelay/presentation/`、`src/openrelay/runtime/orchestrator.py`、`src/openrelay/runtime/commands.py`、`src/openrelay/runtime/restart.py`、`tests/test_runtime.py`、`tests/test_runtime_commands.py`、`tests/test_runtime_help.py`。
- **本轮已收敛**：
  - [x] 独立 design note 已明确 `RuntimeOrchestrator` 的最终职责，不再把它视为 runtime 的总控容器。
  - [x] 已给出 runtime / session / release / presentation 四层的方法归属判断规则。
  - [x] 已按文件列出整理前后的方法持有范围，并明确哪些包装方法应删除、哪些展示逻辑应迁出。
  - [x] 已给出最终目标文件结构，作为后续 runtime 边界重构的稳定落点。
- **后续 follow-up**：
  - [x] 按设计逐步把 `session/ux.py`、`session/list_card.py`、`runtime/panel_service.py` 中的展示逻辑迁到独立 `presentation` 包。
  - [x] 在真正迁移 `RuntimeCommandRouter` 前，先收敛 scope helper 与 status 文案的单一归属，避免同一语义在 runtime / session / presentation 间重复。


### [x] OR-TASK-010 单卡翻页与终极 `/panel` 导航
- **当前状态**：本轮已落地。
- **已完成证据**：`docs/design/panel-single-card-navigation.md`、`README.md`、`src/openrelay/feishu.py`、`src/openrelay/help_renderer.py`、`src/openrelay/panel_card.py`、`src/openrelay/runtime.py`、`src/openrelay/session_list_card.py`、`tests/test_runtime.py`。
- **本轮已收敛**：
  - [x] 独立 design note 已明确单卡导航的信息架构、状态模型、更新目标与返回路径。
  - [x] `/resume list` 与 `/panel sessions` 的分页 / 排序按钮已支持在同一张卡片内完成导航，而不是每次翻页都发新卡。
  - [x] 已落地主 `/panel` 从总览进入子结果面再返回总览的同卡路径，并补上 `/help -> /panel` 的同卡跳转。
  - [x] README、帮助文案与自动化测试已同步新的“导航型卡片优先原地更新”心智，design note 也补了手工验收步骤。
- **后续 follow-up**：
  - [ ] 评估是否把更多纯导航动作继续收敛到同卡更新，而把执行型动作明确维持在文本 / 新消息主路径。
  - [ ] 如果后续出现更深层级的 `/panel` 子菜单，再评估是否需要 breadcrumb 或返回栈，而不是现在就提前引入状态机。

### [x] OR-TASK-009 查询优化与 `/panel` 界面设计
- **当前状态**：第一版已落地。
- **已完成证据**：`docs/design/panel-query-information-architecture.md`、`README.md`、`src/openrelay/panel_card.py`、`src/openrelay/runtime.py`、`src/openrelay/runtime_commands.py`、`src/openrelay/help_renderer.py`、`src/openrelay/session_ux.py`、`tests/test_runtime.py`、`tests/test_runtime_commands.py`。
- **本轮已收敛**：
  - [x] 独立 design note 已明确查询场景、信息架构、结果层级和 `/panel` 的职责边界。
  - [x] `/panel` 已收敛为总入口，并落地 `sessions / directories / commands / status` 四类结果面；其中 `sessions` 支持最小翻页 / 排序闭环。
  - [x] 总览预览项与结果页项已共享同一套 `title / meta / preview / action` 语义，不再各自零散设计。
  - [x] README、`/help` 与自动化测试已同步新的 `/panel` 使用心智。
- **后续 follow-up**：
  - [ ] 评估是否为会话结果补自由文本搜索，而不是只停留在结构化筛选。
  - [ ] 评估是否把 `/resume list` 的分页 / 排序进一步并到单卡 `/panel sessions` 导航里。

### [x] OR-TASK-005 响应卡片对齐 Codex CLI 的样式和配色
- **当前状态**：本轮已落地。
- **已完成证据**：`docs/design/feishu-card-theme.md`、`src/openrelay/card_theme.py`、`src/openrelay/render.py`、`src/openrelay/runtime_live.py`、`src/openrelay/streaming_card.py`、`src/openrelay/help_renderer.py`、`src/openrelay/panel_card.py`、`src/openrelay/session_list_card.py`、`tests/test_render.py`、`tests/test_runtime_live.py`、`tests/test_streaming_card.py`。
- **本轮已收敛**：
  - [x] 独立 design note 已明确样式层级、状态语义和组件映射规则。
  - [x] 主回复卡片与运行中卡片都接入统一主题语义，并分别落地到 `build_reply_card()` 与 live sections / final sections。
  - [x] 渲染实现已收敛到共享 theme shell 与状态语义，不再在多处重复 header/config 特判。
  - [x] 在实际端上观察到 header template 着色不稳定后，状态元信息已进一步收敛到正文 hero / markdown panel，而不是继续依赖 header 颜色。
  - [x] 文档已说明 CLI 视觉特征的保留项与主动舍弃项。
- **后续 follow-up**：
  - [ ] 评估是否把 diff / 日志 / 命令输出再拆成更细粒度的卡片组件映射。
  - [ ] 如果后续需要更强状态颜色语义，再评估 CardKit streaming header 能力是否值得单独利用。

### [x] OR-TASK-001 常用目录的快速切换
- **当前状态**：本轮已落地。
- **已完成证据**：`docs/design/directory-shortcuts.md`、`README.md`、`src/openrelay/config.py`、`src/openrelay/session_ux.py`、`src/openrelay/panel_card.py`、`src/openrelay/runtime.py`、`src/openrelay/help_renderer.py`、`tests/test_config.py`、`tests/test_runtime.py`。
- **本轮已收敛**：
  - [x] 独立 design note 已说明目录来源、命名规则、作用域与冲突策略。
  - [x] `/panel` 已增加配置驱动的常用目录快捷入口，点击后直接复用 `/cwd` 切换。
  - [x] README 与 `/help` 文案已同步到“有快捷目录时优先点按钮”的心智。
  - [x] 已补目录快捷配置解析与按钮切换的自动化测试。
- **后续 follow-up**：
  - [ ] 评估是否继续补“最近目录”而不是只停留在配置驱动快捷目录。
  - [ ] 如果用户侧需要自维护入口，再评估目录别名命令或收藏编辑面板。

### [x] OR-TASK-002 多条连续消息、编辑消息时的用户体验
- **当前状态**：本轮已落地。
- **已完成证据**：`docs/design/consecutive-message-ux.md`、`src/openrelay/follow_up.py`、`src/openrelay/runtime.py`、`src/openrelay/help_renderer.py`、`README.md`、`tests/test_runtime.py`。
- **本轮已收敛**：
  - [x] 独立 design note 已明确 active run、pending inputs、follow-up 合并和用户可见反馈。
  - [x] runtime 串行处理不再只靠隐式等锁，active run 期间的新文本会进入显式 follow-up 队列并按同一主路径 drain。
  - [x] 已覆盖连续发送 / 追加输入，以及 `/stop` 后继续处理 follow-up 两个核心场景。
  - [x] README 与帮助文案已补齐“什么时候直接补充、什么时候 `/stop`、什么时候 `/new`”的用户心智说明。
- **后续 follow-up**：
  - [ ] 如果后续要真正支持编辑 / 撤回，先确认飞书是否提供稳定事件源，再决定是否单独建模。
  - [ ] 评估是否把 follow-up 状态进一步映射到运行中卡片，而不只靠即时确认文本。

### [x] OR-TASK-007 `/help` 卡片化并支持按钮直达执行
- **当前状态**：本轮已落地。
- **已完成证据**：`src/openrelay/help_renderer.py`、`src/openrelay/runtime.py`、`src/openrelay/runtime_commands.py`、`tests/test_runtime.py`、`tests/test_feishu.py`。
- **本轮已收敛**：
  - [x] `/help` 已优先发送交互卡片，展示当前状态、下一步建议、示例提示词和命令分组。
  - [x] 帮助卡片按钮复用现有 card action 上下文，点击后可直接执行 `/status`、`/resume list`、`/new`、`/cwd`、`/main`、`/develop` 等命令。
  - [x] 按钮分组已按“看现场 / 会话管理 / 环境切换 / 配置与控制”收敛，和帮助信息结构保持一致。
  - [x] 已补帮助卡片动作链路测试，覆盖按钮上下文解析与点击后直达命令执行。
- **后续 follow-up**：
  - [ ] 评估是否为“继续当前任务”“总结当前进度”这类非命令主路径补一组稳定提示词按钮。
  - [ ] 继续收敛 `/help`、`/panel`、`/resume list` 三类卡片的视觉层级和组件复用。

### [x] OR-TASK-006 会话列表卡片化、分页与排序
- **当前状态**：本轮已落地。
- **已完成证据**：`docs/design/session-list-cards.md`、`src/openrelay/card_actions.py`、`src/openrelay/session_browser.py`、`src/openrelay/session_list_card.py`、`src/openrelay/runtime.py`、`src/openrelay/runtime_commands.py`、`src/openrelay/panel_card.py`、`src/openrelay/session_ux.py`、`tests/test_session_browser.py`、`tests/test_session_list_card.py`、`tests/test_runtime.py`、`tests/test_feishu.py`。
- **本轮已收敛**：
  - [x] `/resume list` 已改为交互卡片，并展示当前页会话项。
  - [x] 卡片支持显式翻页，上一页 / 下一页动作会保留当前上下文。
  - [x] 卡片支持“最近更新优先 / 当前会话优先”切换，默认是最近更新优先。
  - [x] 恢复会话、翻页、切换排序三类动作都通过命令文本携带状态，并有对应测试覆盖。
- **后续 follow-up**：
  - [ ] 评估是否把 `/panel` 里的会话区域直接收敛到同一套分页卡片入口。
  - [ ] 如果会话规模继续增大，再评估是否从固定页大小切到游标分页。
  - [ ] 评估是否把会话列表卡片和帮助卡片的视觉层级进一步统一。

### [x] OR-TASK-008 运行时模块边界收敛
- **当前状态**：本轮已收敛。
- **已完成证据**：`docs/design/runtime-modularization.md`、`src/openrelay/help_renderer.py`、`src/openrelay/session_browser.py`、`src/openrelay/runtime_commands.py`、`src/openrelay/runtime.py`、`src/openrelay/session_ux.py`、`tests/test_help_renderer.py`、`tests/test_session_browser.py`、`tests/test_runtime_commands.py`。
- **本轮已收敛**：
  - [x] `/help` 展示逻辑从 `runtime.py` 抽成独立模块，并保持现有行为。
  - [x] 会话列表查询 / 恢复与展示格式化拆层，为 `/resume` 卡片分页排序预留稳定接口。
  - [x] 命令路由从 `RuntimeOrchestrator` 主类收敛到 `RuntimeCommandRouter`，`runtime.py` 不再承载主命令分支树。
  - [x] runtime 入口类已从 `AgentRuntime` 更名为 `RuntimeOrchestrator`，显式表达“消息编排器”职责。
  - [x] 已补独立模块测试并完成最小回归与全量回归验证。
- **后续 follow-up**：
  - [ ] 拆出 `/panel` 与 `/resume` 的独立会话列表 / 卡片模块。
  - [ ] 为会话浏览引入更清晰的数据结构，减少 `dict[str, object]` 传递。
  - [ ] 如果命令继续膨胀，再评估把 release / panel 相关 helper 继续从 runtime 中下沉。
  - [ ] 继续评估 `feishu.py` 中 parser / messenger / dispatcher 的边界。

### [x] OR-TASK-004 让 `/stop` 成为可靠的立即中断动作
- **当前状态**：第一版已落地。
- **已完成证据**：`docs/design/stop-command.md`、`src/openrelay/runtime.py`、`src/openrelay/backends/codex.py`、`tests/test_runtime.py`、`tests/test_codex_backend.py`。
- **本轮已收敛**：
  - [x] runtime 会先确认“已发送停止请求，正在中断当前回复”。
  - [x] Codex backend 已补上请求级取消，不再只依赖 turn 运行阶段的中断。
  - [x] 请求阶段取消会重置当前 session 绑定的 app-server client，避免悬挂请求残留。
  - [x] 停止完成后会清理 active run、typing 和流式回复收尾。
- **后续 follow-up**：
  - [ ] Claude 等其他 backend 的中断语义和 Codex 对齐。
  - [ ] `/stop` 后更细粒度的中间输出保留策略。
  - [ ] 多会话、多终端场景下更完整的抢占与接管模型。

## 使用约定

- 新任务优先放进 `Ready`，并给出稳定的 `OR-TASK-xxx` 编号。
- `Ready` 区块按优先级排序：`P0 > P1 > P2 > P3`；同级任务按当前推进顺序排。
- 任务进入实现阶段时，可以临时挪到 `In Progress`；如果当前仓库不需要显式区分，保持在原区块也可以，但要更新子项和证据。
- 任务一旦满足关闭条件，就把主复选框改成 `[x]`，并把条目移动到 `Landed / Follow-up`。
- 任务如果只完成一部分，不要勾选主复选框；只更新子项、证据和 follow-up。
