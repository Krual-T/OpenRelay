# Detailed Design

## Runtime Verification Plan
本包是设计债务治理任务，不需要真实飞书运行验证。验证重点是任务包结构、目标包分层和后续 handoff 是否清楚。

主验证路径：
1. 执行 `openharness check-tasks`，确认 active package 结构合法。
2. 人工复核 `OR-010` 到 `OR-013` 的 `STATUS.yaml`、`README.md`、`04-verification.md`，确认 OR-017 的分层没有遗漏明显事实。
3. 下一轮实际推进目标包时，把结果写回目标包自身，而不是继续堆在 OR-017。

Fallback：
- 如果目标包状态和证据互相矛盾，先在目标包内修正状态事实，再推进设计。
- 如果某个目标包范围已经超过原包边界，在目标包内拆新任务，OR-017 只记录顺序调整。

预期证据：
- `openharness check-tasks` 输出。
- OR-017 当前文档中的分层表和推进顺序。
- 后续目标包自身的验证和 evidence 写回。

## Files Added Or Changed
- `docs/task-packages/legacy-design-package-maturation/01-requirements.md`
  - 用中文补齐目标用户、核心场景、成功指标、非目标、约束和 counterexample。
- `docs/task-packages/legacy-design-package-maturation/02-overview-design.md`
  - 记录历史包成熟度分层、边界、排序理由和不纳入范围。
- `docs/task-packages/legacy-design-package-maturation/03-detailed-design.md`
  - 记录下一步执行顺序、验证路径、失败处理和归档条件。
- `docs/task-packages/legacy-design-package-maturation/STATUS.yaml`
  - 推进到 `detailed_ready`，表示成熟化计划已经具体到可执行。

目标包自身后续会被修改，但不在本轮直接修改：
- `docs/task-packages/workspace-shortcuts-and-directory-maintenance/`
- `docs/task-packages/current-session-control-surface/`
- `docs/task-packages/unified-waiting-interactions/`
- `docs/task-packages/asynchronous-lookback-experience/`

## Interfaces
稳定边界：
- OR-017 只输出排序、成熟口径和 handoff 规则。
- 目标包负责承载自己的需求、设计、实现、验证和证据。
- `AGENTS.md` 和 `openharness check-tasks` 负责约束任务包位置与结构。

可观测入口：
- `STATUS.yaml` 的 `status`、`updated_at`、`done_criteria`。
- `04-verification.md` 的 `Latest Result`。
- `05-evidence.md` 的 follow-up 是否仍包含阻塞项。

## Stage Gates
- 测试策略：本包只跑 `openharness check-tasks`；目标包进入实现时再运行目标测试。
- 可观测要求：每个目标包必须能从 `STATUS.yaml` 和 `04` / `05` 判断真实阶段，不能只看 README 摘要。
- 实现落点：实际成熟化改动必须落到目标包自身目录。
- 迁移顺序：先 OR-013 收口，再 OR-011，后 OR-010，最后 OR-012。
- 证据类型：结构检查、文档 gate 复核、目标包后续测试和真实运行证据。

## Execution Sequence
1. `OR-013 Workspace Shortcuts And Directory Maintenance`
   - 先修 `README.md` 与 `STATUS.yaml` 状态不一致。
   - 复核 `/shortcut` 卡片化维护路径是否已经满足 done criteria。
   - 如果已满足，补 `04-verification.md` 和 `05-evidence.md` 后进入 `verifying`；如果未满足，在 OR-013 内补详细设计或实现。
2. `OR-011 Current Session Control Surface`
   - 先补需求 gate：当前会话状态模型、高频动作、低频动作下沉、不做项。
   - 再探索现有 `/status`、`/stop`、session lock、reply policy 和 panel 表面。
   - 目标是推进到 `detailed_ready`，为 OR-010 和 OR-012 提供状态边界。
3. `OR-010 Unified Waiting Interactions`
   - 基于 OR-011 的状态模型收敛等待态分类。
   - 明确 terminal interaction、user input、MCP elicitation 的统一回复入口和提交反馈。
   - 目标是把已有 presentation / Feishu 测试证据整理成可执行详细设计。
4. `OR-012 Asynchronous Lookback Experience`
   - 在状态模型和等待态语义稳定后，设计异步回看摘要、停止原因、下一步建议和历史恢复入口。
   - 目标是避免回看体验重复定义当前会话状态。

## Decision Closure
接受：先收口 OR-013，因为它已有实现和测试证据，最可能最快减少一个 active package。

接受：OR-011 先于 OR-010 / OR-012，因为当前会话状态是等待交互和异步回看的共同基础。

拒绝：让 OR-017 替代目标包详细设计。原因是这会制造新的中心化事实源，和仓库 task package 体系冲突。

延期：OR-014 的 detailed design 不在本包内排序。触发条件是用户明确要求重新排全量 active package，或 OR-014 阻塞上述历史包。

## Error Handling
主要失败路径：
- 状态文件和 README 不一致，导致协作者误判进度。
- 目标包实际已有代码证据，但文档仍停留在占位状态。
- OR-017 被继续扩写成任务板，目标包本身没有变成熟。

处理方式：
- 状态不一致时优先修目标包状态事实。
- 实现证据缺失时，不把包推进到 `verifying`。
- 如果某个目标包开始实际推进，OR-017 只记录 handoff，不承载目标包细节。

## Migration Notes
本包从 `proposed` 推进到 `detailed_ready` 后，后续工作应迁移到目标包自身。

归档条件：
1. `OR-010` 到 `OR-013` 均至少被复核一次，并且不再处于“只有占位设计、没有下一步”的状态。
2. `OR-013` 的状态不一致已处理。
3. 至少一个目标包完成 handoff 并在自己的 `04` / `05` 中留下新证据。
4. `openharness check-tasks` 通过。

回滚触发点：如果发现 OR-017 的分层误导了实际优先级，应先更新 OR-017 的排序理由，再继续推进目标包；不要在目标包里反向引用过期排序。

## Detailed Reflection
测试视角挑战：设计债务包没有代码测试，是否能称为 `detailed_ready`。处理结果：接受文档型验证路径，但要求 `openharness check-tasks` 和目标包事实复核，不能声称产品功能完成。

架构视角挑战：OR-011、OR-010、OR-012 之间可能形成循环依赖。处理结果：用状态模型作为先后边界，先让 OR-011 定义最低状态语义，再让 OR-010 和 OR-012 分别消费它。

流程视角挑战：如果 OR-017 长期不归档，会持续占一个 active package。处理结果：设定归档条件，尤其要求至少一次目标包 handoff 作为 OR-017 完成证据。
