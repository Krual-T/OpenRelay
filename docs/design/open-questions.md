# Design Task Board

更新时间：2026-03-10

这份文档不再只是记录“开放问题”，而是作为 `openrelay` 当前设计与实现任务的任务板。

原则很简单：
- 一个条目就是一个可独立推进的任务，不再只停留在问题描述。
- 主复选框表示“这个任务已经可以关闭”；不是“已经讨论过”。
- 任务关闭前，优先补齐设计 note、实现边界、验证方式和后续 follow-up。
- Codex CLI 只能在满足关闭条件后自己勾选主复选框；详细规则见 `docs/design/task-board-protocol.md`。

## Ready

### [ ] OR-TASK-007 `/help` 卡片化并支持按钮直达执行
- **优先级**：P1
- **目标**：让用户打开 `/help` 时直接看到可点击的操作按钮，减少记忆命令和手动输入成本。
- **当前关注**：帮助内容里哪些命令适合按钮化；按钮点击后如何稳定复用当前会话上下文；帮助卡片与现有 `/panel` 交互是否要统一风格；文本帮助是保留兜底还是直接收敛到卡片；群聊、私聊、线程回复场景下按钮动作是否都能正确回到当前会话。
- **关闭条件**：
  - [ ] `/help` 至少提供一个交互卡片版本，并展示核心帮助信息与可点击按钮。
  - [ ] 点击按钮后可直接执行对应命令，不需要用户再手动输入。
  - [ ] 按钮分组与帮助信息结构保持一致，主路径短且可扫描。
  - [ ] 至少补一条帮助卡片动作相关测试，或给出明确的手工验收步骤。
- **建议产物**：`docs/design/` 下的专题 note（如需要）；`src/openrelay/runtime.py`、`src/openrelay/panel_card.py` 或独立帮助卡片模块、`src/openrelay/feishu.py`、`tests/test_runtime.py` 等对应实现。

### [ ] OR-TASK-002 多条连续消息、编辑消息时的用户体验
- **优先级**：P1
- **目标**：让用户在“连续输入”和“边想边补充”的真实使用习惯下，不会感到混乱，也不会误以为机器人漏看了消息。
- **当前关注**：连续消息是排队、合并还是 follow-up；上一条未完成时如何提示；编辑 / 撤回如何响应；typing、流式卡片、状态提示在排队 / 追加 / 覆盖 / 取消场景下如何表现；群聊、私聊、线程回复是否要分策略。
- **关闭条件**：
  - [ ] 独立 design note 明确状态模型、优先级规则和用户可见反馈。
  - [ ] runtime 串行处理与 active run 模型按设计收敛，不再依赖模糊约定。
  - [ ] 至少覆盖连续发送、追加输入、取消或编辑中的两个核心场景。
  - [ ] README 或帮助文案补齐用户心智说明。
- **建议产物**：`docs/design/` 下的专题 note；`src/openrelay/runtime.py`、`src/openrelay/runtime_live.py`、`src/openrelay/streaming_card.py` 等对应实现。

### [ ] OR-TASK-001 常用目录的快速切换
- **优先级**：P2
- **目标**：让用户在飞书里切换到常用工作目录时，操作足够短、足够稳定、足够可预期。
- **当前关注**：常用目录 / 收藏目录 / 最近目录；目录别名；`/panel` 快捷切换；配置作用域；和 `main / develop` 工作区切换的配合。
- **关闭条件**：
  - [ ] 独立 design note 说明目录来源、命名规则、作用域与冲突策略。
  - [ ] 至少一条最小交互路径落地，例如目录别名、收藏目录或 `/panel` 快捷入口。
  - [ ] README 与 `/help` 文案同步。
  - [ ] 至少一条针对目录切换行为的测试或明确的手工验收步骤。
- **建议产物**：`docs/design/` 下的专题 note；`src/openrelay/runtime.py`、`src/openrelay/panel_card.py`、`src/openrelay/session_ux.py` 等对应实现。

### [ ] OR-TASK-005 响应卡片对齐 Codex CLI 的样式和配色
- **优先级**：P2
- **目标**：让飞书中的响应卡片在保持平台适配性的前提下，尽量继承 Codex CLI 清晰、克制、可扫描的界面体验，使用户在两个界面之间切换时不需要重新适应信息表达方式。
- **当前关注**：整体视觉语言是否收敛到接近 Codex CLI；标题、正文、代码块、命令、文件路径、状态提示等层级如何映射到卡片组件；成功、进行中、失败、已取消是否要有稳定的颜色语义；代码块、diff、日志、命令输出是否要分样式；飞书卡片能力受限时哪些特征保留、哪些简化；样式配置应挂在哪一层。
- **关闭条件**：
  - [ ] 独立 design note 明确样式层级、状态语义和组件映射规则。
  - [ ] 至少一个主回复卡片和一个运行中卡片完成样式收敛。
  - [ ] 渲染实现收敛到统一主题约定，而不是零散特判。
  - [ ] 文档说明哪些 CLI 视觉特征保留、哪些主动舍弃。
- **建议产物**：`docs/design/` 下的专题 note；`src/openrelay/render.py`、`src/openrelay/runtime_live.py`、`src/openrelay/panel_card.py`、`src/openrelay/streaming_card.py` 等对应实现。

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
  - [x] 命令路由从 `AgentRuntime` 主类收敛到 `RuntimeCommandRouter`，`runtime.py` 不再承载主命令分支树。
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
