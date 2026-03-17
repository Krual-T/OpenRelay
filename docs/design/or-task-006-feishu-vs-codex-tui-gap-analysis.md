# OR-TASK-006 Codex TUI 与 OpenRelay 飞书端体验差距调研

更新时间：2026-03-18

## 调研目的

这份文档回答一个具体问题：

- 以 `codex-cli 0.115.0` 在本机可见能力为基线，当前 `openrelay` 飞书端离「接近 Codex TUI 原生体验」还差什么？
- 哪些差距已经有后端 typed contract 支撑、只是飞书侧还没做？
- 哪些差距并不只是飞书 UI 没做，而是当前 external `codex app-server` / `openrelay` runtime contract 还没有完整承接？

这里不讨论 Claude 路径，也不讨论“飞书是否应该完全复刻终端 UI”；重点是识别真实主路径差距，并判断优先级。

## 证据基线

### 1. 本机 Codex 可见能力（2026-03-18 实测）

本机 `codex --version` 输出为 `codex-cli 0.115.0`。

通过 `codex --help` 与实际启动交互式界面，可确认当前公开能力至少包括：

- 默认直接进入交互式 TUI
- 顶层 CLI 子命令：`exec`、`review`、`login`、`logout`、`mcp`、`mcp-server`、`app-server`、`apply`、`resume`、`fork`、`cloud`、`features`
- 交互式界面内至少暴露 `/model`、`/compact` 等内建命令提示
- CLI 级运行参数：`--model`、`--sandbox`、`--ask-for-approval`、`--search`、`--cd`、`--add-dir`、`--no-alt-screen`

相关官方页面：

- https://developers.openai.com/codex/cli
- https://developers.openai.com/codex/config
- https://developers.openai.com/codex/config-advanced

### 2. openrelay 当前主线路径（仓库现状）

当前仓库已经明确：

- `openrelay` 主 backend 是 external `codex app-server`，基线为 `codex >= 0.115.0`
- 飞书端已支持真实 session 续接、thread 绑定、streaming transcript、`/panel`、`/resume`、`/compact`、`/cwd`、`/model`、`/sandbox`、`/stop`
- command / file change / permissions approval 已有交互闭环
- `item/tool/requestUserInput` 与 `mcpServer/elicitation/request` 已进入统一 `user_input` 语义
- `terminal.interaction` 已被识别成独立运行时事件，但还没有真正的交互闭环

主要代码证据：

- `README.md`
- `docs/design/codex-app-server-event-consumption-detailed-design.md`
- `src/openrelay/runtime/commands.py`
- `src/openrelay/runtime/turn.py`
- `src/openrelay/runtime/interactions/controller.py`
- `src/openrelay/backends/codex_adapter/mapper.py`
- `src/openrelay/backends/codex_adapter/semantic_mapper.py`
- `src/openrelay/backends/codex_adapter/backend.py`
- `src/openrelay/agent_runtime/backend.py`
- `src/openrelay/presentation/live_turn.py`

## 先给结论

如果把目标定义为“飞书端能承接大部分 Codex TUI 的日常远程工作流”，当前差距可以分成三层：

### A. 已有基础，但体验还不够像 TUI

这类问题不是没有能力，而是还没有把能力组织成更顺手的飞书交互：

1. 命令面不完整，且没有形成“飞书卡片 == TUI 控制台”的统一入口。
2. approval 已有闭环，但 user input 仍偏文字回填，缺少结构化卡片化回答体验。
3. transcript 虽然已经收敛到单条卡片，但缺少更强的“当前运行焦点 / 最近一步 / 可继续动作”组织。
4. session 恢复虽然可用，但缺少 fork、read transcript、会话对比这类 TUI 常见续接动作。

### B. openrelay runtime 已收到事件，但还没把它做成可操作体验

这类是最值得优先补的：上游 contract 已经有，飞书端只是还没闭环。

1. `terminal.interaction` 现在只记录，不可回复。
2. `item/tool/requestUserInput` / `mcpServer/elicitation/request` 已映射到 `user_input`，但还没有真正的表单型卡片答案体验。
3. tool / plan / system event 已入 runtime state，但缺少更强的“过程导航”和“异常定位”呈现。

### C. 当前仍明显弱于 TUI，且不只是飞书前端问题

这类差距需要区分：有些是 `openrelay` 没接，有些是 external app-server 本身还没把 TUI 的全部本地交互暴露出来。

1. `fork` 目前没有进入 `openrelay` 命令面，也没有 backend-neutral 对应接口。
2. TUI 的本地能力入口（如 `login`、`logout`、`cloud`、`features`、`completion`）并不适合直接投影成飞书命令，目前也没有明确产品化策略。
3. 终端内的键盘级操作、焦点切换、滚动查看、即时 slash-command 补全，不可能一比一映射到飞书线程，需要重做交互模型，而不是“补齐几个命令”就能解决。

## 现状对齐：哪些能力已经不算差距

先把已经有的能力排除掉，避免误判。

### 1. 真实 session 续接：已具备主路径能力

这块 `openrelay` 已经不是 demo 状态：

- `/resume` 已支持连接后端原生会话
- backend 已支持 `list_sessions()`、`read_session()`、`compact_session()`
- `BackendTurnSession` 会在 `SessionStartedEvent` 后尽早持久化 native thread id
- 飞书 thread 与 relay session / backend session 已形成绑定

对应证据：

- `src/openrelay/runtime/panel_service.py`
- `src/openrelay/agent_runtime/service.py`
- `src/openrelay/backends/codex_adapter/backend.py`
- `src/openrelay/runtime/turn.py`

这说明“不能续接真实会话”已经不是当前主矛盾。

### 2. 过程流式投影：已具备可用基础

虽然飞书不可能复制 alt-screen，但当前已经有：

- streaming card
- transcript-first final card
- reasoning / tool / plan / approval / observe notice 进入同一份 live state
- `/stop` 中断当前运行

对应证据：

- `src/openrelay/runtime/turn.py`
- `src/openrelay/presentation/live_turn.py`
- `src/openrelay/feishu/reply_card.py`
- `docs/design/feishu-tui-transcript-rendering-plan.md`

### 3. approval 闭环：已不再是 0 到 1 问题

当前已支持：

- command approval
- file change approval
- permissions approval
- provider resolved event 清理 pending state

对应证据：

- `src/openrelay/runtime/interactions/controller.py`
- `src/openrelay/backends/codex_adapter/mapper.py`
- `src/openrelay/backends/codex_adapter/turn_stream.py`

所以这里的差距不再是“有没有 approval”，而是“approval 和其他交互是否够顺手”。

## 主要差距清单

## 一、命令面与入口组织仍明显弱于 TUI

### 差距 1：飞书命令面只覆盖了 openrelay 本地控制，不等于 Codex TUI 可见命令面

当前 `openrelay` 命令面集中在：

- session / scope：`/panel`、`/resume`、`/compact`、`/cwd`、`/main`、`/develop`、`/shortcut`
- run control：`/stop`、`/clear`、`/model`、`/sandbox`、`/backend`
- utility：`/status`、`/help`、`/ping`、`/restart`

证据：

- `README.md`
- `src/openrelay/runtime/commands.py`
- `src/openrelay/runtime/help.py`

而当前 Codex 公开可见命令面至少还包括：

- `fork`
- `review`
- `exec`
- `apply`
- `cloud`
- `mcp` / `mcp-server`
- `features`
- `login` / `logout`

其中有三类情况：

1. **应补齐到飞书主路径的**：`fork`
2. **可以考虑做成管理卡片，但不应直接等价暴露的**：`review`、`exec`、`apply`
3. **更像本机环境管理，不一定应该进飞书聊天主路径的**：`login`、`logout`、`completion`、`features`、`cloud`

判断：

- 当前最真实的差距，不是“把所有 CLI 子命令照搬成 slash command”，而是没有完成一份“哪些 TUI 能力应该以飞书原生方式出现”的产品映射表。
- 在没有映射策略前，用户会自然感受到“飞书里只是一个可聊天的 relay，不像一个完整的 Codex 工作台”。

建议优先级：`P1`

### 差距 2：缺少统一的“运行中控制台卡片”入口

虽然 `/panel`、`/help`、`/resume` 都已有卡片，但运行中真正高频的几个动作还没被收进一个固定控制面：

- 停止本轮
- 查看当前 session / native thread
- 切 model
- 切 sandbox
- compact 当前会话
- fork 当前会话（未实现）
- 打开最近可恢复会话

TUI 的一个核心体验不是“命令多”，而是“所有控制都围绕当前会话就地发生”。

飞书目前更像：

- 过程卡片是一张
- `/panel` 是另一张
- `/help` 是另一张
- approval / input request 又是另一张

这会导致控制入口分散。

建议：把当前运行中 transcript card 旁边稳定补一个轻量 command strip，或者允许从同一张 card 打开 session control 子视图。

建议优先级：`P1`

## 二、终端交互还没有真正闭环

### 差距 3：`terminal.interaction` 已进入 runtime，但当前只看得到，回不去

这是当前最明确的功能缺口之一。

现状：

- `semantic_mapper` 已把 `item/commandExecution/terminalInteraction` 收敛成 `terminal.interaction`
- reducer 会把它保存到 `state.terminal_interactions`
- 设计文档也已把它列为进入主路径的 typed event

但实际上：

- `BackendTurnSession._handle_runtime_event()` 只对 `ApprovalRequestedEvent` 做显式交互处理
- `RunInteractionController` 没有处理 terminal stdin 请求的分支
- `AgentBackend` / `AgentRuntimeService` 也没有“向运行中 terminal interaction 回写 stdin”这条公共接口

对应证据：

- `src/openrelay/backends/codex_adapter/semantic_mapper.py`
- `src/openrelay/agent_runtime/reducer.py`
- `src/openrelay/runtime/turn.py`
- `src/openrelay/agent_runtime/backend.py`

这意味着：

- 现在飞书端最多只能知道“底层命令在等输入”
- 但用户无法像在 TUI 那样继续把输入送给那个 terminal process

这不是简单前端问题，而是 runtime contract 缺口。

建议：

1. 在 `agent_runtime` 增加 `TerminalPrompt` / `TerminalInputDecision` 一类统一模型，别把它继续塞进 observe notice。
2. 在 backend protocol 增加 `respond_terminal_interaction(...)`。
3. 飞书侧用卡片按钮 + 文本输入双通道承接：
   - 常见动作：`Enter` / `y` / `n` / `continue`
   - 自定义输入：回复文本
4. resolved 后原地更新同一张卡片，而不是新起一条纯文本消息。

建议优先级：`P0`

## 三、user input 已映射，但飞书侧还没形成结构化问答体验

### 差距 4：`item/tool/requestUserInput` 与 `mcpServer/elicitation/request` 目前仍偏“文本回填”

这块已经比“完全不支持”更进一步，但离 TUI 级顺手体验还有差距。

现状：

- `CodexProtocolMapper.map_server_request()` 已把两类请求映射为 `ApprovalRequest(kind="user_input")`
- `RunInteractionController._request_user_input_decision()` 已能区分 tool questions 和 MCP elicitation
- `_ask_tool_question()` 已支持选项按钮和纯文本回答

对应证据：

- `src/openrelay/backends/codex_adapter/mapper.py`
- `src/openrelay/runtime/interactions/controller.py`

但问题在于：

1. 交互模型仍是“问题逐个发出来 -> 用户在线程回复文本或点按钮”。
2. 多题表单没有被收敛成一张结构化卡片。
3. `isSecret` 只做了文字警告，飞书侧没有更强的私密输入策略。
4. MCP elicitation 的 schema 还没有变成真正的表单渲染，只是退化成普通问答。

因此用户体验上仍会像：

- backend 在“向你要结构化输入”
- 飞书只是在“让你继续聊天回复”

而不是“系统弹出一张可提交的交互表单”。

这正是你提到“应该可以用飞书卡片进行选择”的那类差距。

建议：

1. 对 `tool_questions` 先做有限集合支持：单选、多选、自由输入、是否允许 other。
2. 对 `mcp_elicitation` 至少先支持：message + URL + 简单 schema 字段渲染。
3. 卡片提交后原地更新为“已提交 / 已取消”，不要留下悬空问题。
4. 对 `isSecret` 类型明确策略：
   - 要么直接声明不支持 secret input
   - 要么引入单次短链 / 私聊跳转 / 本机确认，不要只靠风险提示。

建议优先级：`P0`

## 四、会话操作仍缺一块：fork

### 差距 5：有 resume / compact，没有 fork

本机 `codex --help` 已公开 `fork`，这是 TUI 工作流里很重要的一种操作：

- 保留上下文
- 沿另一条思路试验
- 不污染原会话

而 `openrelay` 当前：

- 有 `/resume`
- 有 `/compact`
- backend-neutral protocol 没有 `fork_session`
- 飞书卡片也没有“从当前 thread 派生新 thread / 新 relay session”的动作

对应证据：

- 本机 `codex --help` 实测
- `src/openrelay/agent_runtime/backend.py`
- `src/openrelay/backends/codex_adapter/backend.py`
- `src/openrelay/runtime/commands.py`

这会导致飞书端虽然能“接回过去”，但不能“沿当前思路分叉”，体验上仍弱于 TUI。

建议：

1. 先确认 external `app-server` 是否已有稳定 fork RPC；如果没有，需要评估是否走 CLI 辅助路径，或先在产品层标注为 blocker。
2. 在 runtime 增加 `fork_session(locator, scope)` 能力。
3. 飞书侧把它做成：
   - 当前 session 控制卡片里的“Fork 当前会话”
   - `/fork [current|<session_id>|latest]`

建议优先级：`P1`

## 五、过程可见性仍弱于 TUI 的“当前焦点感”

### 差距 6：transcript 有了，但“当前正在干什么”还不够强

当前 `LiveTurnPresenter` 已经能展示：

- reasoning
- plan
- tool lifecycle
- approval
- backend observe notice

但飞书端仍缺少 TUI 那种很强的当前焦点感：

- 当前正在执行哪个命令
- 最近失败的是哪一步
- 正在等待什么输入
- 本轮计划与已完成步骤的短摘要

`build_live_status_view()` 已有一定尝试，但更多还是 markdown 摘要，而不是真正把“当前焦点”稳定钉在可视区域。

对应证据：

- `src/openrelay/presentation/live_turn.py`
- `src/openrelay/runtime/rendering.py`

建议：

1. 在 streaming card 顶部保留固定的当前焦点条：`Thinking / Running command / Waiting for input / Waiting for approval / Finishing`。
2. 把最后一个失败命令、最后一个 plan step、最后一个 user-facing blocker 做成单独 facts 区。
3. 把“继续动作”做成按钮，而不是只体现在文本里。

建议优先级：`P1`

## 六、当前 session 读历史能力没有真正进入飞书日常路径

### 差距 7：backend 已支持 `read_session`，但飞书端没有把“读 transcript / 看旧会话内容”做成显式能力

现状：

- runtime backend 已定义 `read_session()`
- Codex backend 已实现 `read_session()`
- 但飞书命令面与卡片里没有稳定入口让用户查看旧会话 transcript 摘要

对应证据：

- `src/openrelay/agent_runtime/backend.py`
- `src/openrelay/backends/codex_adapter/backend.py`
- `src/openrelay/runtime/commands.py`

这会导致：

- `/resume` 更像“盲选会话 id 再接回去”
- 缺少“先看一下这条会话是什么，再决定要不要接”的缓冲层

建议：

- 在 `/resume` 列表卡片上增加“查看摘要”动作
- 或在 `/panel sessions` 中增加“展开最近一轮 transcript / 首尾消息”视图

建议优先级：`P2`

## 七、TUI 的本机控制能力并不适合直接搬运，但当前也缺少产品边界说明

### 差距 8：哪些能力不应该进飞书，当前没有明确产品边界

例如：

- `login` / `logout`
- `completion`
- `features`
- `cloud`
- `mcp-server`

这些命令未必应该作为飞书会话命令出现，因为它们更像：

- 本机环境维护
- 账号状态管理
- 开发者工具
- 实验入口

如果硬搬进飞书，反而会让产品边界变乱。

但如果完全不说明，用户又会感到“为什么 TUI 有这些，飞书里没有”。

建议：

- 在 `/help` 或 README 明确区分：
  - `会话内能力`
  - `本机环境能力`
  - `暂未远程化的 TUI 专属能力`

这不是实现问题，而是认知一致性问题。

建议优先级：`P2`

## 建议的实施顺序

### 第一阶段：先补真正阻塞远程可用性的交互闭环

1. `terminal.interaction` 可回复化
2. `user_input` 卡片表单化
3. 运行中卡片增加固定焦点区与继续动作

这三项做完，飞书端就不再只是“看得到执行过程”，而是能承接更多 TUI 在 terminal 里发生的中断式互动。

### 第二阶段：补足 session 工作流

1. `fork`
2. session transcript 摘要查看
3. 当前 session 控制卡片统一化

这三项做完，飞书端会更像“远程工作台”，而不只是“可聊天的 session relay”。

### 第三阶段：收敛产品边界

1. 明确哪些 TUI 命令不会远程化
2. 明确哪些能力转成卡片动作而不是 slash command
3. 让 `/help`、README、`/panel` 对同一套能力边界说同一种话

## 建议拆分的任务

### P0

- `terminal.interaction` runtime contract + Feishu reply card 闭环
- `user_input` / MCP elicitation 卡片表单化

### P1

- current session control card
- `fork` 能力调研与接入
- transcript card 顶部焦点区增强

### P2

- session transcript 摘要查看
- `/help` / README 产品边界说明补齐
- TUI -> Feishu 能力映射表文档化

## 最终判断

如果只看“能不能远程驱动 Codex 做事”，`openrelay` 已经跨过了最难的 0 到 1。

但如果目标是“让飞书端在主观体验上接近 Codex TUI”，当前最明显的差距已经不是 session、streaming 或 approval 本身，而是两类中断式交互还没完全产品化：

1. terminal interaction
2. structured user input / elicitation

再往上一个层次，则是 session 工作流还缺 fork，以及运行中控制入口仍然分散。

所以这轮调研后的结论可以收敛成一句话：

> 当前 openrelay 飞书端已经具备“远程跑 Codex”的主骨架，但离“像 Codex TUI 一样顺手”还差一个完整的交互闭环层；最先要补的不是更多展示，而是让等待用户参与的运行时事件真正可操作。
