# Detailed Design

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Runtime Verification Plan
第一阶段详细设计尚未完成。本包当前只定义详细设计必须回答的问题。

- Verification Path:
  1. 先用 Markdown 矩阵列出功能、实际副作用和验证证据。
  2. 再选 3 条代表性功能做真实飞书手动触发 dry run。
  3. 用 `openrelay-trace` 或 SQLite 查询确认消息链路。
  4. 同步调研飞书官方 CLI / 官方调试工具能否补充 UI 或事件观测。
- Fallback Path:
  - 如果官方工具不能观测卡片流式 UI，则真实 UI 观察由人工完成，系统侧判断由 `openrelay-trace` 完成。
  - 如果 trace 中缺少关键阶段，则不能宣称真实运行验证闭环完成，应转入 Log Manager 或 observability 后续任务。
- Planned Evidence:
  - 功能清单文件。
  - 验证矩阵文件。
  - 官方飞书工具调研记录。
  - 至少一条真实飞书触发后的 trace 查询证据。

只有当详细设计已经具体到可以执行时，才进入 `in_progress`。
如果设计已经完成但实现尚未开始，应保持在 `detailed_ready`。

## Files Added Or Changed
- `docs/task-packages/feature-inventory-runtime-verification/README.md`
  - 本 task package 入口。
- `docs/task-packages/feature-inventory-runtime-verification/01-requirements.md`
  - 记录清单和真实运行验证的需求边界。
- `docs/task-packages/feature-inventory-runtime-verification/02-overview-design.md`
  - 记录功能清单、实际副作用、验证矩阵的总体结构。
- 后续详细设计应决定是否新增：
  - `docs/features.md`
  - `docs/runtime-verification-matrix.md`
  - `docs/research/feishu-official-cli-verification.md`
  - 或机器可读的 `docs/runtime-verification-matrix.yaml`

## Interfaces
待详细设计确认的稳定接口：

- `openrelay-trace`：查询消息事件时间线。
- SQLite message trace：验证 ingress、session、turn、reply 等阶段。
- 飞书官方 CLI / 官方调试工具：待确认是否能查询消息、事件、卡片 update 或流式 UI。
- 未来可能新增的 openrelay 验证 CLI：读取矩阵并对照 trace 输出判断结果。

## Stage Gates
- 第一版功能清单字段已确定。
- 第一版验证矩阵字段已确定。
- 官方飞书工具调研步骤已具体到资料来源和待执行命令。
- 至少 3 条真实运行验收用例已写成可执行步骤。
- 明确哪些证据来自 UI 人工观察，哪些证据来自本地结构化 trace。

## Decision Closure
接受：真实运行验证必须覆盖到飞书触发后的系统事实，不能只停留在 `pytest`。

拒绝：现在直接假设飞书官方 CLI 能判断流式 UI 是否正确。原因是官方能力未验证。

延期：是否实现矩阵自动判定 CLI。触发条件是矩阵字段稳定，且至少 3 条手动验收用例能通过 trace 复现。

## Error Handling
静默出错风险：用户在飞书看到“有回复”，但 backend turn 没有实际执行，或者回复来自错误 session。矩阵必须要求同时检查 UI 结果和 runtime trace，避免把表面回复当成真实执行成功。

如果官方工具查询不到 UI 状态，不应把“没有查到异常”解释为 UI 正常。

## Migration Notes
建议迁移顺序：

1. 先落文档清单和矩阵。
2. 再用真实飞书手动用例校准矩阵字段。
3. 再决定是否扩展 `openrelay-trace` 或新增验证 CLI。
4. 最后把高频功能的真实运行验证纳入常规发布前检查。

回滚触发点：如果矩阵维护成本明显高于收益，应收缩到 10 个最高频功能，不追求全量覆盖。

## Detailed Reflection
当前详细设计还不够进入实现阶段。下一步应先进入探索：确认飞书官方 CLI / 官方调试工具真实能力，并盘点现有 trace 是否足以支持“用户触发，我来验证”的工作流。
