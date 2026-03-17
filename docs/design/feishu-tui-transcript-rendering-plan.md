# Feishu TUI Transcript Rendering

更新时间：2026-03-17

## 背景

当前 `openrelay` 在飞书里对 live turn 的渲染，采用的是“运行中状态卡片 + 最终答案卡片”的双区模型：

- streaming 阶段：`FeishuStreamingSession` 只更新单个 markdown element；
- live 内容：`src/openrelay/feishu/reply_card.py` 里的 `_streaming_inline_content()` 先渲染 `history_items`，再把 `partial_text` 作为正文拼进去；
- final 阶段：`build_complete_card()` 把过程日志放进默认折叠的 `collapsible_panel`，把最终答案放在 panel 外的主 markdown。

这条链路在 CardKit 上工作正常，但它的表达模型和 Codex TUI 不同。TUI 的核心体验不是“状态面板 + 答案面板”，而是“单条 transcript 按时间线向前生长”。用户看到的是同一条消息里的：

- 执行记录
- 解释文字
- 中间结论
- 最终结论
- follow-up 建议

这些内容自然混排，而不是先放进过程面板、再在下面补答案。

本设计的目标不是把 Feishu 伪装成终端，而是让 Feishu 投影层和 TUI 更接近同一个产品语义：**渲染统一 transcript，而不是分别渲染‘过程’与‘答案’**。

## 本轮落地结果

本轮已经把 OR-TASK-003 的主路径落地到代码里，当前实现收敛为：

- `src/openrelay/presentation/live_turn.py`
  - `build_snapshot()` 现在会同时维护 `plan_history_items` 与 `transcript_items`。
  - `build_transcript_markdown()` 成为 presenter 的正式 transcript 输出。
  - `build_final_card()` / `build_streaming_card()` 直接面向 transcript card，而不是 `process_text`。
- `src/openrelay/feishu/reply_card.py`
  - `render_transcript_markdown()` 成为统一 transcript renderer。
  - `build_streaming_content()` 与 `build_complete_card()` 都改为 transcript-first。
  - `build_process_panel_text()` 仅保留为兼容别名，不再代表 panel-first 主路径。
- `src/openrelay/feishu/streaming.py`
  - `freeze()` 超时后不再构造“运行中状态 panel card”，而是冻结 transcript card，并在正文尾部追加 timeout notice。
- `src/openrelay/runtime/orchestrator.py`
  - `_reply_final()` 不再手工拼 `process_text`，而是直接关闭到 presenter 提供的 final transcript card。
- `src/openrelay/runtime/turn.py`
  - 中断/停止也走同一条 final transcript card 主路径，不再分叉到旧的 panel 输出。

这意味着当前飞书 live turn 主路径已经不再依赖：

- `Execution Log`
- `collapsible_panel`
- `process_text + final_answer` 这种双区 contract

而是统一依赖：

- `transcript_items`
- `render_transcript_markdown(...)`
- `build_complete_card(..., transcript_markdown=...)`

## 当前实现链路

### 1. 运行时快照构建

入口类：`src/openrelay/presentation/live_turn.py` 的 `LiveTurnPresenter`

当前关键方法：

- `create_initial_snapshot()`
- `build_snapshot()`
- `_history_items()`
- `build_process_text()`
- `build_final_reply()`
- `build_reply_card()`

当前结构特点：

- `LiveTurnPresenter` 已经把 reasoning、tool、plan、approval、backend event 收敛为 `history_items`。
- `partial_text` 保存当前 assistant 输出。
- 但 presenter 目前没有“统一 transcript”这个显式概念；它只提供：
  - 过程文本：`build_process_text()`
  - 最终回复：`build_final_reply()`
  - 最终卡片：`build_reply_card()`

也就是说，presentation 层目前输出的仍是“双区 contract”。

### 2. 飞书流式拼装

入口类：`src/openrelay/feishu/streaming.py` 的 `FeishuStreamingSession`

当前关键方法：

- `start()`
- `update()`
- `update_card_content()`
- `freeze()`
- `close()`

当前结构特点：

- 卡片在 `start()` 时先建一个固定 streaming card。
- `update()` 期间持续调用 `build_streaming_content(live_state)`，只更新 card 里的一个 markdown element。
- 超过 streaming window 后，`freeze()` 会切成“运行中状态”最终卡片，仍然沿用“panel + answer”模型。

### 3. 飞书卡片渲染

入口文件：`src/openrelay/feishu/reply_card.py`

当前关键方法：

- `build_process_panel_text()`
- `_streaming_inline_content()`
- `build_streaming_content()`
- `_build_process_panel_element()`
- `build_complete_card()`

当前结构特点：

- `build_process_panel_text()` 只负责 history / process 面板。
- `_streaming_inline_content()` 用 `process_text + --- + partial_text` 组 streaming 正文。
- `build_complete_card()` 用 `collapsible_panel(process_text) + markdown(final_answer)` 组最终卡片。

因此当前问题并不是“样式不对”，而是 reply card 层内建了一个双区结构假设。

### 4. 最终消息发布

入口类：`src/openrelay/runtime/orchestrator.py` 的 `RuntimeOrchestrator`

当前关键方法：

- `_reply_final()`

当前结构特点：

- `_reply_final()` 仍显式拿 `build_process_panel_text(live_state)` 生成 `process_text`。
- 然后调用 `self.live_turn_presenter.build_reply_card(text, process_text=process_text)`。

这说明 runtime 主路径仍把“过程文本”当成 final reply 的一等输入，而不是把 presenter 当作统一 transcript 提供者。

## 目标结构

目标是引入一个新的 presentation contract：

- live turn 的主输出是 `transcript_markdown`
- streaming 与 final 共用同一条 transcript 生成链
- Feishu card 只负责“承载 transcript”，不再主导内容分区

这里需要进一步写死一个实现约束：**最终 contract 应优先是 transcript-first，而不是把最新状态快照重新排版得更像 transcript。**

也就是说，目标不只是把当前 `history_items + partial_text` 改成线性文本，而是要明确：

- transcript 代表一条按时间线生长的消息历史；
- 渲染层首先关心“追加了什么 block”，其次才是“当前状态长什么样”；
- 只有确实需要覆盖更新的 live block，才允许在 transcript 尾部做受控替换；
- 不能继续让 `plan`、`summary`、assistant partial 这些内容停留在“当前状态板块”的语义里。

也就是把现有 contract：

- `process_text`
- `final_answer`
- `build_reply_card(text, process_text=...)`

收敛成：

- `build_transcript(snapshot)`
- `build_streaming_card(transcript)`
- `build_final_card(transcript)`

更准确地说，最终应该是：

1. `LiveTurnPresenter` 负责把 `LiveTurnViewModel` 投影成 transcript 语义块。
2. `reply_card.py` 负责把 transcript 语义块渲染成 Feishu markdown / card。
3. `FeishuStreamingSession` 只负责流式更新 card，不再拥有内容分区逻辑。
4. `RuntimeOrchestrator` 不再额外拼 `process_text`。

### Transcript Contract

为了避免实现落回“状态快照投影”，这里补充 transcript contract：

1. transcript 的基本单元是 presentation block，而不是 provider event，也不是拼好的整段 markdown。
2. transcript block 默认采用 append-only 语义；只有少数 live block 允许覆盖最后一个同类 block。
3. assistant partial / final text 属于 transcript block，不再是 panel 外单独的“正文区”。
4. `summary` 仍保留 `---` 分隔线，但它属于 transcript 内的普通 block，而不是特殊的“切换到正文区”信号。
5. runtime 元信息默认不进入主 transcript，除非它已经被定义为用户可感知事件。

当前已识别出的“默认不进入主 transcript”的元信息包括：

- `rate_limits`
- `thread_status`
- `available_skills`
- `last_diff_id`

这些信息如果后续仍有展示价值，应进入 debug / compact / diagnostics 视图，而不是主回复正文。

### Plan 语义补充

`plan` 是当前最容易因为状态模型而退化的部分，这里单独补充：

- Codex / TUI 语义更接近“plan 更新历史”，而不是“始终只有一个当前 plan 面板”。
- 因此 `plan.updated` 进入 transcript 时，默认应保留历史痕迹，而不是每次只覆盖 `state.plan_steps` 后再渲染成单个板块。
- 允许的收敛方式应是：
  - 追加新的 `plan` block；或
  - 只覆盖 transcript 尾部最后一个仍处于 live 状态的 `plan` block。
- 不应继续采用“飞书只维护一个当前 Plan 板块”的展示语义。

如果实现上仍保留 `LiveTurnViewModel.plan_steps` 作为便捷快照字段，也只能把它视为派生缓存，不能再把它当作 transcript 的唯一来源。

## 建议改动

### A. `LiveTurnPresenter`：从“双输出”改为“统一 transcript 输出”

文件：`src/openrelay/presentation/live_turn.py`

建议新增方法：

- `build_transcript_snapshot(self, state: LiveTurnViewModel, *, previous: dict[str, Any] | None = None, session: SessionRecord | None = None, format_cwd: Callable[...] | None = None) -> dict[str, Any]`
- `build_transcript_markdown(self, state: dict[str, Any] | LiveTurnViewModel) -> str`
- `build_streaming_card(self, state: dict[str, Any] | LiveTurnViewModel) -> dict[str, object]`
- `build_final_card(self, state: dict[str, Any] | LiveTurnViewModel, *, fallback_text: str = "") -> dict[str, object]`

建议删除或降级为兼容层的方法：

- `build_process_text()`
- `build_reply_card()`

建议改动思路：

- `build_snapshot()` 可以保留，继续作为底层状态快照构建器。
- 在 presenter 层显式引入“transcript 是主输出”的概念，避免 orchestrator 和 reply_card 各自再拼一遍。
- `build_transcript_markdown()` 应把以下内容按时间线线性展开：
  - `history_items`
  - 当前 reasoning 文本
  - 当前 assistant partial / final text
  - approval resolved 等保留交互项
- 展开顺序应遵守“先事件，再输出”的心智，不再区分“panel 区”和“answer 区”。
- 这里要特别避免把 transcript 实现成“每轮根据最新 `state` 全量重建一块 Plan / Tool / Summary 面板”；否则视觉上线性，语义上仍是状态投影。

建议新增私有方法：

- `_build_transcript_blocks(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]`
- `_merge_transcript_blocks(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]`

这里的 block 不是 provider event，而是 presentation block，例如：

- `history_block`
- `reasoning_block`
- `assistant_block`
- `interaction_block`
- `summary_block`

这样可以保持 presenter 仍是 backend-neutral，而不是把 Codex 的事件名直接打进飞书层。

额外要求：

- presenter 需要显式区分“append block”与“replace tail block”两种操作语义。
- `plan`、assistant partial、正在运行中的 command detail 都应归入这套语义，而不是被塞回统一的状态面板。

### B. `reply_card.py`：从“panel builder”改为“transcript renderer”

文件：`src/openrelay/feishu/reply_card.py`

建议新增方法：

- `render_transcript_markdown(state: dict[str, Any] | None) -> str`
- `build_transcript_streaming_card(transcript_markdown: str) -> dict[str, Any]`
- `build_transcript_final_card(transcript_markdown: str, *, summary_text: str = "") -> dict[str, Any]`

建议删除或弃用的方法：

- `build_process_panel_text()`
- `_build_process_panel_element()`
- `_streaming_process_text()`

建议重写的方法：

- `_streaming_inline_content()`
- `build_streaming_content()`
- `build_complete_card()`

具体思路：

1. 把 `_streaming_inline_content()` 改为简单代理：
   - 不再做 `process_text + --- + partial_text` 拼接；
   - 直接返回 `render_transcript_markdown(live_state)`。

2. 把 `build_complete_card()` 改为 transcript-only：
   - 默认不再创建 `collapsible_panel`；
   - 卡片 body 只保留一个 markdown element；
   - `summary` 可以继续从 transcript 里抽；
   - reasoning 不再从正文剥离后放到 panel，除非后续明确保留一个可配置 compact mode。

3. 保留 markdown 平台适配工具：
   - `optimize_markdown_style()`
   - `split_reasoning_text()`
   - `strip_markdown_for_summary()`

但它们的角色应变成“排版修整”，而不是“内容拆区”。

4. 把 `_render_history_items()` 的输出要求从“适合 panel 阅读”调整成“适合插入 transcript 阅读”：
   - 当前树形结构、短摘要和 worked-for 尾行可保留；
   - 但不要再假定它必然出现在折叠 panel 里。
   - `summary` 的 `---` 需要保留，但它的作用是 transcript block 分隔，而不是“过程区 / 正文区”的切换标记。

### C. `FeishuStreamingSession`：只负责流式更新，不再决定内容结构

文件：`src/openrelay/feishu/streaming.py`

建议改动方法：

- `freeze()`
- `update()`
- `close()`

建议改动思路：

- `update()` 期间继续只更新单个 markdown element，这一点不需要变。
- 但它不应再依赖“streaming 内容”和“final 卡片”是两套语义。
- `freeze()` 在 streaming window 到期后，应切换到“冻结后的 transcript card”，而不是“运行中状态 panel card”。
- `close()` 应接收 presenter 构造好的 final transcript card，而不是依赖外部先算 `process_text`。

建议保持不变的方法：

- `start()`
- `update_card_content()`
- `set_streaming_mode()`
- `update_card_json()`

这些方法本质是 transport / CardKit 操作，和 transcript 设计无关。

### D. `RuntimeOrchestrator`：移除对 `process_text` 的显式依赖

文件：`src/openrelay/runtime/orchestrator.py`

建议改动方法：

- `_reply_final()`

当前问题：

- `_reply_final()` 手动调用 `build_process_panel_text(live_state)`，说明 orchestrator 仍知道飞书 reply 的内部结构。

目标改法：

- 让 `_reply_final()` 只关心“拿最终 card 并发送/关闭 streaming”。
- 由 `LiveTurnPresenter` 直接暴露：
  - `build_final_card(live_state)` 或
  - `build_final_card_from_text(text, live_state)`

建议迁移结果：

- runtime 主路径不再知道 `Execution Log`
- runtime 主路径不再知道 `collapsible_panel`
- runtime 主路径不再知道 `process_text`

这一步很重要，因为如果 orchestrator 还保留这些知识，后续即使表面换成 transcript，结构耦合也还在。

## 迁移顺序

### Phase 1：先引入 transcript builder，不改外部行为

涉及文件：

- `src/openrelay/presentation/live_turn.py`
- `src/openrelay/feishu/reply_card.py`

步骤：

1. 在 `LiveTurnPresenter` 新增 `build_transcript_markdown()`。
2. 在 `reply_card.py` 新增 `render_transcript_markdown()`。
3. 保持旧的 `build_process_panel_text()` 和 `build_complete_card()` 仍可工作。

目标：

- 先把新 contract 建起来；
- 不在第一步同时拆 streaming 和 final。

### Phase 2：把 streaming 改成 transcript-only

涉及文件：

- `src/openrelay/feishu/reply_card.py`
- `src/openrelay/feishu/streaming.py`
- `src/openrelay/runtime/turn.py`

步骤：

1. 让 `build_streaming_content()` 直接返回 transcript markdown。
2. 去掉 `_streaming_inline_content()` 中固定的 `---`。
3. 验证 running 状态下，执行记录、解释文字和 partial answer 能在线性正文里同时出现。

目标：

- 先把最明显的 TUI 差异去掉；
- streaming 体验先和最终态收敛。

### Phase 3：把 final card 改成 transcript-only

涉及文件：

- `src/openrelay/feishu/reply_card.py`
- `src/openrelay/presentation/live_turn.py`
- `src/openrelay/runtime/orchestrator.py`

步骤：

1. 引入 `build_final_card()`。
2. `RuntimeOrchestrator._reply_final()` 改为只调用 presenter 提供的 final card。
3. 删除 `collapsible_panel` 主路径。

目标：

- 把“过程 panel”从主路径移除；
- 让 final reply 和 streaming reply 共享同一个 transcript contract。

### Phase 4：收尾兼容与测试收敛

涉及文件：

- `tests/test_live_turn_presenter.py`
- `tests/test_feishu.py`
- 新增 `tests/test_feishu_reply_card.py` 或等价测试文件

步骤：

1. 删除不再需要的 `process_text` 断言。
2. 为 transcript 混排补测试。
3. 决定是否保留 feature flag，例如：
   - `FEISHU_TRANSCRIPT_RENDER_MODE=transcript|compact`

目标：

- 如果要保留回退路径，这一阶段再决定；
- 不建议在最开始就把回退策略写死进主路径。

## 最小测试矩阵

至少应覆盖下面这些场景：

1. `reasoning + tool + partial_text`
   - streaming 内容里应按线性顺序同时出现三类信息。

2. `command completed + assistant final answer + follow-up suggestion`
   - final card 不应再把 command 结果放进折叠 panel。

3. `pending approval`
   - transcript 中仍能看到审批请求和后续恢复记录。

4. `freeze on streaming timeout`
   - 超时后显示的仍是 transcript，只是不再流式更新。

5. `stop / interrupted`
   - 中断卡片也走 transcript 主路径，不额外分叉到旧 panel 模型。

## 风险与取舍

### 1. 风险：transcript 过长，飞书阅读压强上升

这是最现实的代价。原方案把过程折叠，是为了降低正文噪音；改成 transcript 后，信息会更完整，但也更长。

建议：

- 先追求主语义正确；
- 再决定是否保留 compact mode，而不是为了“看起来简洁”继续维持双区结构。
- 当前实现保留了 `build_process_panel_text()` 兼容入口，必要时可以短期回退调用方，但它已经只是 transcript renderer 的别名，不再单独维护 panel 逻辑。

### 2. 风险：reasoning 与 answer 边界变弱

当前 panel 把 reasoning 隐式折起来，用户比较容易区分“过程”和“结论”。改成 transcript 后，边界需要靠文案和块顺序表达。

建议：

- 不要重新引入 panel；
- 通过统一的 block 标题和节奏控制解决，例如 `Thinking`、`Ran`、`Updated files`、最终正文之间保留稳定分隔。

### 3. 风险：runtime 层继续偷偷依赖旧结构

如果只改 `reply_card.py`，但 `RuntimeOrchestrator` 仍然传 `process_text`，那只是把旧模型藏起来，没有真正收敛。

建议：

- 这一轮设计必须明确 orchestrator 也要减负；
- transcript 应由 presenter 提供，不应由 runtime 主流程手拼。

## 明确不做的事

- 不在这轮设计里把 Feishu 做成真正终端模拟器。
- 不把 provider 原始事件名直接暴露给飞书 UI。
- 不在这轮里同时重做 `/panel`、`/help`、审批卡片等非 live turn 主路径。
- 不为了兼容旧 panel 先长期保留双轨主路径；如果需要回退，只允许短期 feature flag。

## 最小验证

本轮已通过下面的最小验证：

- `uv run pytest tests/test_runtime_turn.py tests/test_live_turn_presenter.py tests/test_feishu_streaming.py`

覆盖点包括：

- transcript streaming 与 final card 共用同一条 markdown 输出链；
- `plan` 更新会保留 transcript 历史，而不是只显示最后一个当前 plan；
- timeout freeze / stop interrupt 都会落到 transcript-only card；
- `build_complete_card()` 会优先渲染外部传入的 transcript markdown，而不是重新拆出 panel。

## 结论

这次改动的核心不是“把卡片改好看一点”，而是把 Feishu live turn 的渲染 contract 从：

- `process_text + final_answer`

收敛为：

- `transcript_markdown`

一旦这件事成立，TUI 那种“执行记录 + 解释文字 + follow-up 建议”自然混排的体验，在飞书上就具备了结构前提。之后剩下的只是 markdown 排版和压缩策略，而不再是主模型冲突。
