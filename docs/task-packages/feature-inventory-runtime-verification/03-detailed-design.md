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

## Completion Plan
本包不需要继续扩展功能清单范围；完成口径应从“继续补更多表格”收敛为“把关键真实运行证据补到足以归档”。

### Closure Lane A: stop control
- 目标功能：`F-010-stop`。
- 触发方式：在真实飞书会话里启动一条可持续一段时间的普通消息，再发送 `/stop`。
- 必要证据：
  - `openrelay-trace --db ~/.openrelay/data/openrelay.sqlite3 --message-id "$STOP_MESSAGE_ID" --json` 能看到 `/stop` command 分支和停止确认回复。
  - 被停止的 run 没有继续产生 stale streaming update。
  - 人工观察飞书端能看到停止确认，且原回复状态不误导用户继续等待。
- 通过后写回：
  - `docs/runtime-verification-matrix.md` 的 `Executed Dry Runs`。
  - 本包 `04-verification.md` 与 `05-evidence.md`。

### Closure Lane B: card action follow-up
- 目标功能：至少覆盖 `F-011-card-pagination`、`F-012-card-form-action` 或 `/resume` 连接后的后续回复其中一类。
- 推荐优先级：先用 `/resume` 成功回复子 thread，因为真实问题已经暴露过会话错乱，且当前矩阵已经记录过相关 trace。
- 必要证据：
  - card action incoming event 可以定位到原卡片、按钮动作和回复消息。
  - 成功回复消息的后续用户消息进入正确本地会话，不串到顶层会话或另一条恢复会话。
  - trace、`session_key_aliases`、`relay_session_bindings` 能互相解释同一个结果。
- 通过后写回：
  - `docs/runtime-verification-matrix.md` 增加一条 card action 执行样例。
  - 若发现 `/resume` 生命周期语义仍不清晰，把产品语义留给 `OR-018`，本包只记录验证缺口和证据。

### Closure Lane C: card sender observability
- 当前缺口：`/help`、`/resume`、`/workspace` 的 interactive card 能从飞书消息查询看到，但本地 trace 没有等价的 `egress/reply.sent` 事件。
- 两种可接受完成方式：
  1. 直接补 card sender 的结构化 trace，并重新验证 `/help`、`/resume`、`/workspace` 至少一条。
  2. 如果本轮不改 observability，则新增或关联后续任务，把“card sender trace 缺口”明确移出本包完成口径；本包归档时只能宣称矩阵已识别缺口，不能宣称卡片发送全自动可判定。
- 推荐方向：若要让 `OR-015` 作为发布前验证基线，优先补 trace；否则本包会长期停在人工观察依赖上。

### Status Gate
- 满足 Lane A、Lane B，并对 Lane C 做出“补 trace”或“拆后续任务”的明确处理后，状态可从 `detailed_ready` 推进到 `verifying`。
- `verifying` 阶段必须重新运行 `openharness check-tasks`，并至少运行与 `/resume`、reply policy、message observability 相关的目标测试。
- 只有当 `04-verification.md` 的 `Latest Result` 不再是 `insufficient_verification`，且 `05-evidence.md` 的 follow-up 不再包含阻塞型证据缺口时，才能归档。

## Detailed Reflection
测试视角挑战：矩阵不能把 `lark-cli` 查询到消息当作 UI 通过。处理结果：接受，所有流式卡片相关条目都要求 `real_feishu_manual`，CLI 只作为辅助。

架构视角挑战：清单如果直接做成机器可读格式，可能在字段未稳定前增加维护成本。处理结果：暂缓，先用 Markdown 表格稳定语义。

风险视角挑战：现有 trace 对 CardKit 中间更新缺少结构化事件，只能用最终 `reply.sent.payload.streaming=true` 和日志辅助判断。处理结果：接受为残余风险，后续如果真实 dry run 需要自动判定流式细节，再拆 observability 增强任务。

完成口径挑战：如果继续要求覆盖全部 14 个功能，本包会变成无止境的验收清单。处理结果：拒绝全量阻塞归档，改为以 stop、card action、card sender observability 三类当前最高风险缺口作为归档前硬门槛，其余功能保留在矩阵中按后续发布节奏补证据。
