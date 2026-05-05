# Detailed Design

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Runtime Verification Plan
第一阶段详细设计已落成文档化清单和矩阵。本包不直接实现新的 runtime 代码。

- Verification Path:
  1. 使用 `docs/feature-inventory.md` 作为功能清单。
  2. 使用 `docs/runtime-verification-matrix.md` 作为功能到证据的判断表。
  3. 使用 `docs/research/feishu-official-runtime-tools.md` 作为官方工具能力边界。
  4. 真实飞书 dry run 从 `message_id` 进入 `uv run openrelay-trace --message-id "$MESSAGE_ID" --json`。
  5. 对照矩阵判断 UI、runtime 分支、状态持久化和 reply 证据。
- Fallback Path:
  - 如果官方工具不能观测卡片流式 UI，则真实 UI 观察由人工完成，系统侧判断由 `openrelay-trace` 完成。
  - 如果 trace 中缺少关键阶段，则不能宣称真实运行验证闭环完成，应转入 Log Manager 或 observability 后续任务。
- Planned Evidence:
  - `docs/feature-inventory.md`
  - `docs/runtime-verification-matrix.md`
  - `docs/research/feishu-official-runtime-tools.md`
  - 后续至少一条真实飞书触发后的 trace 查询证据。

当前设计已经具体到可以执行真实验收，但尚未执行真实飞书客户端 dry run，因此状态停在 `detailed_ready`。

## Files Added Or Changed
- `docs/task-packages/feature-inventory-runtime-verification/README.md`
  - 本 task package 入口。
- `docs/task-packages/feature-inventory-runtime-verification/01-requirements.md`
  - 记录清单和真实运行验证的需求边界。
- `docs/task-packages/feature-inventory-runtime-verification/02-overview-design.md`
  - 记录功能清单、实际副作用、验证矩阵的总体结构。
- 后续详细设计应决定是否新增：
  - 已新增 `docs/feature-inventory.md`
  - 已新增 `docs/runtime-verification-matrix.md`
  - 已新增 `docs/research/feishu-official-runtime-tools.md`
  - 暂不新增机器可读的 `docs/runtime-verification-matrix.yaml`

## Interfaces
本轮确认的稳定接口：

- `openrelay-trace`：查询消息事件时间线。
- SQLite message trace：验证 ingress、session、turn、reply 等阶段。
- 飞书官方 CLI：作为可选辅助，用于发送消息、查询消息和监听事件；不能单独证明真实客户端流式 UI。
- 未来可能新增的 openrelay 验证 CLI：读取矩阵并对照 trace 输出判断结果。

## Stage Gates
- 第一版功能清单字段已确定，并覆盖 14 个高频功能。
- 第一版验证矩阵字段已确定，并给出 `pytest`、`local_trace`、`sqlite_state`、`real_feishu_manual`、`official_cli_optional` 的证据分类。
- 官方飞书工具调研已具体到资料来源、可用命令和不能证明的 UI 能力。
- 至少 3 条真实运行验收用例可从矩阵执行：`F-002-status`、`F-008-normal-turn`、`F-009-streaming-card`、`F-010-stop`。
- 已明确哪些证据来自 UI 人工观察，哪些证据来自本地结构化 trace。

## Decision Closure
接受：真实运行验证必须覆盖到飞书触发后的系统事实，不能只停留在 `pytest`。

拒绝：现在直接假设飞书官方 CLI 能判断流式 UI 是否正确。原因是官方能力未验证。

延期：是否实现矩阵自动判定 CLI。触发条件是至少 3 条手动验收用例能通过 trace 复现。

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
测试视角挑战：矩阵不能把 `lark-cli` 查询到消息当作 UI 通过。处理结果：接受，所有流式卡片相关条目都要求 `real_feishu_manual`，CLI 只作为辅助。

架构视角挑战：清单如果直接做成机器可读格式，可能在字段未稳定前增加维护成本。处理结果：暂缓，先用 Markdown 表格稳定语义。

风险视角挑战：现有 trace 对 CardKit 中间更新缺少结构化事件，只能用最终 `reply.sent.payload.streaming=true` 和日志辅助判断。处理结果：接受为残余风险，后续如果真实 dry run 需要自动判定流式细节，再拆 observability 增强任务。
