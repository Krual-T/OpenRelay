# Overview Design

## System Boundary
本包覆盖历史迁移包的成熟化计划，具体范围是 `OR-010`、`OR-011`、`OR-012`、`OR-013`。这些包已经是正式 task package，但成熟度不一致，后续需要按优先级补齐设计、实现或验证证据。

本包不覆盖：
- `OR-014 Log Manager`：它有独立 overall design 和直接 detailed-design follow-up，不再由本包排序。
- `OR-015 Feature Inventory And Runtime Verification`：它是新近验证基线任务，不是历史迁移包。
- `OR-018 Resume Binding Lifecycle`：它来自新的真实运行问题，不是历史迁移债务。
- archived packages：归档包只作为历史证据，不重新纳入 active package 集合。

## Proposed Structure
成熟化计划分三层：

1. `inventory layer`：标出目标包当前成熟度和缺口。
2. `sequence layer`：给出下一轮推进顺序，并说明排序原因。
3. `handoff layer`：一旦开始某个目标包，就回到该包自身的 `01` 到 `05` 文件推进，OR-017 只记录顺序和门槛。

当前分层结果：

| Package | Current reading | Main gap | Maturation target |
| --- | --- | --- | --- |
| `OR-011 Current Session Control Surface` | 仍是 `proposed`，但它影响停止、状态、继续等待、压缩上下文等高频控制 | 当前会话状态模型和控制入口边界不够具体 | 先补需求与概览设计，给后续实现一个统一控制面 |
| `OR-010 Unified Waiting Interactions` | 仍是 `proposed`，已有部分 presentation / feishu 测试证据 | 等待态分类、卡片语义和输入提交反馈还没收敛 | 在 OR-011 的状态模型之后补详细设计，避免等待态入口和控制入口重复 |
| `OR-012 Asynchronous Lookback Experience` | 仍是 `proposed`，偏产品体验闭环 | 依赖当前会话状态、历史恢复入口和 transcript 摘要语义 | 放在 OR-011 / OR-010 后，避免先设计回看摘要却缺少稳定状态来源 |
| `OR-013 Workspace Shortcuts And Directory Maintenance` | `STATUS.yaml` 已是 `in_progress`，已有代码和测试证据；`README.md` 仍写 `proposed` | 状态文档不一致，且卡片化维护路径是否已满足 done criteria 需要复核 | 用户已明确该功能开发优先级较低，先 hold；后续只在收尾窗口处理状态一致性和验证复核 |

## Key Flows
主路径：

1. 先用 OR-017 明确目标包成熟度和推进顺序。
2. 选择一个目标包后，进入目标包自身目录补写或实现，不继续扩写 OR-017。
3. 每完成一个目标包的阶段，更新该目标包的 `STATUS.yaml`、`04-verification.md` 和 `05-evidence.md`。
4. 当 `OR-010` 到 `OR-013` 都不再处于占位设计状态，OR-017 可进入 `verifying` 并准备归档。

失败信号：
- 目标包的 `README.md` 与 `STATUS.yaml` 状态不一致。
- 目标包声称 ready，但 `01` 到 `03` 不能回答 stage gate 问题。
- 目标包实际实现已发生，但 `04` / `05` 没有记录测试和证据。
- 协作者需要回 legacy notes 才能知道下一步怎么做。

降级方向：
- 如果一次性成熟化 4 个包成本过高，先推进 `OR-011`，让状态模型稳定下来；`OR-013` 暂时 hold，不因它更接近收尾就压过更高风险的会话语义问题。
- 如果某个包在探索时发现范围过大，应在该包内拆新任务，不扩大 OR-017。

## Stage Gates
- 已列出 `OR-010` 到 `OR-013` 的成熟度、主要缺口和目标门槛。
- 已明确 `OR-014`、`OR-015`、`OR-018` 不属于本包范围。
- 已给出非编号排序的推荐顺序：`OR-011` 定状态模型，`OR-010` 收敛等待交互，`OR-012` 做异步回看，`OR-013` 功能开发先 hold。
- 已记录失败信号和降级方向。

## Trade-offs
备选方案一：按编号从 `OR-010` 顺序推进到 `OR-013`。

拒绝原因：编号顺序不能反映当前风险。`OR-011` 的状态模型会影响 `OR-010` 和 `OR-012`，应优先于它们成熟；`OR-013` 虽然更接近收尾，但属于工作区快捷功能开发，用户已明确优先级较低。

备选方案二：把所有历史包的详细设计都写进 OR-017。

拒绝原因：这会让 OR-017 变成新的中心任务板，违反仓库“每个设计任务以自己的 task package 为事实来源”的约定。

## Overview Reflection
产品视角挑战：是否应该先做用户最明显的等待态体验，而不是先做 OR-011。处理结果：延期到 OR-010，但不优先于 OR-011；原因是等待态需要依赖当前会话状态和控制入口，否则容易做出另一套分散入口。

架构视角挑战：OR-013 已经是 `in_progress`，是否还应该排在最前面。处理结果：不再排最前；接受它仍在 OR-017 清单中，但先 hold，只在后续收尾窗口修状态一致性并复核 done criteria。

流程视角挑战：OR-017 是否可以直接归档。处理结果：暂不归档；本轮已让它达到 `detailed_ready`，但归档前还应至少完成一次目标包 handoff，证明该计划能实际减少活跃债务。
