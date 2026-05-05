# Detailed Design

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Runtime Verification Plan
- Verification Path:
  1. 先补或确认单元测试：连续点击同一张 `/resume` 卡片的两个连接按钮必须生成两个不同本地会话和两个不同 alias session key。
  2. 验证成功回复文案：必须明确“回复本条消息继续该会话”，并包含 `session_id` 与 `cwd`。
  3. 验证 scope 解析：成功回复 message id、thread id、parent id 写入 `session_key_aliases` 后，后续普通消息能解析回对应本地会话。
  4. 验证 binding 一致性：更新后的 `relay_session_bindings.native_session_id` 不应被旧 `sessions.native_session_id` 反向覆盖。
  5. 真实运行验证：在真实飞书里发送 `/resume`，连续点击两条不同后端会话，分别回复两条成功消息，用 `openrelay-trace --db ~/.openrelay/data/openrelay.sqlite3 --message-id <message_id> --json` 或 SQLite 查询确认后续回复分别命中正确 `relay_session_id` 与 `native_session_id`。
- Fallback Path:
  - 如果真实飞书事件字段不足以自动验证，保留人工操作步骤，并把原卡片 message id、两个成功回复 message id、后续回复 message id、SQLite 查询结果写入 evidence。
  - 如果真实服务暂时不可重启或不可点击卡片，本轮最多停在 `detailed_ready`，不进入 `verifying` 或 `archived`。
- Planned Evidence:
  - 单元测试命令输出。
  - 至少一条真实 `/resume` card action 点击链路。
  - 两个成功回复 message id 与后续回复 trace。
  - `sessions`、`session_key_aliases`、`relay_session_bindings` 的对应查询。

只有当开始补实现或补真实验证证据时，才进入 `in_progress` 或 `verifying`。
当前文档推进完成后应进入 `detailed_ready`，不宣称实现或真实验证已经完成。

## Files Added Or Changed
- `docs/task-packages/resume-binding-lifecycle/*`：承载 OR-018 的需求、架构、实施与验证口径。
- `src/openrelay/feishu/parsing.py`：如后续发现真实 card action 字段缺失，改这里补字段解析；本层不写生命周期判断。
- `src/openrelay/session/scope/resolver.py`：如 alias 解析或 outbound alias 生成缺口暴露，改这里收敛入口归属。
- `src/openrelay/runtime/command_handlers/runtime_session.py`：承载 `/resume` 目标解析、恢复 scope 生成和命令限制。
- `src/openrelay/runtime/command_services/runtime_session_commands.py`：承载 backend session 读取、绑定和成功文案。
- `src/openrelay/runtime/reply_service.py` 与 `src/openrelay/runtime/replying.py`：承载成功回复路由、强制新消息、alias 写入和 reply trace。
- `src/openrelay/runtime/message_dispatch.py` 或执行协调相关模块：如果实施 native-session 级串行化，落点应在 execution key 或 coordinator，而不是 command handler。
- `tests/runtime/test_command_router_resume.py`、`tests/session/test_scope_resolver.py`、`tests/runtime/test_reply_policy.py`、`tests/feishu/test_parsing.py`：分别覆盖恢复命令、scope alias、回复路由和 card action 字段解析。

## Interfaces
- `IncomingMessage.session_key`：显式 session key 优先，只表示调用方已经知道目标 scope；解析层不验证它是否代表恢复入口。
- `SessionScopeResolver.build_session_key()`：按显式 key、root id、thread candidates、顶层命令和 message id scope 的顺序解析。恢复入口后续回复必须通过 alias 命中已创建 scope。
- `SessionScopeResolver.remember_outbound_aliases()`：成功回复 message id 和 thread id 是恢复入口可持续的关键契约；`alias_session_key` 必须指向新建恢复 scope。
- `RuntimeSessionCommandHandler._resume_scope_key()`：card action 恢复入口必须包含事件或消息维度和目标 `native_session_id`，避免同一原卡片的多个按钮共享 scope。
- `SessionMutationService.bind_native_thread_to_new_session()`：每次成功连接创建新的本地 session；binding 更新以后，后续读取以 binding hydration 为准。
- `MessageDispatchService.build_execution_key()`：当前按 `relay_session_id` 串行；若同一 `native_session_id` 并发被证明不安全，需要扩展为 native-session 级锁或复合锁。
- Observability：`message_event_log` 至少应能看到 incoming message id、reply message id、session key、relay session id、native session id。无法自动记录 card sender 时，需要人工飞书消息查询补证据。

## Stage Gates
- 测试策略：先跑 `/resume`、scope resolver、reply policy、parsing、message observability 目标测试，再做真实飞书验证。
- Observability 要求：真实验证必须能对应成功回复 message id、后续回复 message id、`relay_session_id` 和 `native_session_id`。
- 实现落点：入口创建不下沉到 Feishu parsing，入口解析不塞进 command handler，binding attachment 不回退到只读 `sessions.native_session_id`。
- 迁移顺序：先补测试，再补 alias/scope/binding/文案，再补并发保护或明确残余风险，最后采真实 trace。
- 证据类型：单元测试输出、真实飞书 message id、trace JSON 或 SQLite 查询。

## Decision Closure
- 接受：每次成功 `/resume` 连接创建独立本地会话，保证飞书入口隔离。
- 接受：成功回复消息是用户继续入口，顶层普通消息不继承恢复会话。
- 接受：短期允许同一个后端会话存在多个本地入口，但必须处理或显式记录 native-session 并发风险。
- 拒绝：用原卡片 `open_message_id` 作为唯一恢复入口标识；同一张卡片多次点击会复用这个 id。
- 拒绝：把 `/resume` 设计成顶层默认会话切换；它无法支持多个恢复入口。
- 延期：入口关闭、归档、清理、入口数量上限和复用提示。

## Error Handling
- 静默串线：后续回复命中错误 alias 或顶层 scope。发现方式是 trace 的 `session_key`、`relay_session_id`、`native_session_id` 与成功回复证据不一致。
- 原卡片覆盖：同一张 `/resume` 卡片连续点击两个连接按钮，第二次覆盖第一次。防护是恢复 scope 必须包含目标 `native_session_id` 和事件维度。
- binding 回退：旧 `sessions.native_session_id` 覆盖新 binding。防护是读取路径用 binding hydrate，并用测试覆盖绑定更新。
- native-session 并发：两个本地会话同时驱动同一个 backend 会话。防护候选是执行层 native-session 级锁；如果本轮不实现，必须在验证风险里明示。
- 用户误用：在顶层发消息以为能继续恢复会话。防护是成功文案明确“回复本条消息继续”，并保持顶层隔离。

## Migration Notes
- 第一阶段：保持现有数据库结构，不做 schema migration。
- 第二阶段：补充或确认现有测试覆盖 `/resume` 多入口、成功文案、scope alias 和 binding 更新。
- 第三阶段：如需要实现 native-session 级串行化，先在测试中复现两个 `relay_session_id` 指向同一 `native_session_id` 的并发风险，再改 execution key 或 coordinator。
- 第四阶段：重启真实 openrelay 后执行真实飞书验证，证据写入 `04-verification.md` 和 `05-evidence.md`。
- 回滚触发：如果新 scope 生成导致 card pagination 或非 resume card action 不能工作，应回滚 `/resume` 专属 scope 变化，而不是回滚整个 session alias 机制。

## Detailed Reflection
测试视角挑战：已有测试能证明两个 card action 生成不同 alias，但不能单独证明飞书后续普通回复会带哪些 root/thread 字段。处理结果：把真实飞书后续回复 trace 列为进入 `verifying` 的硬证据。

架构视角挑战：native-session 级锁可能跨越 command、dispatch、execution 多层，直接塞进 `/resume` 会污染边界。处理结果：接受执行层作为唯一合理落点；如果暂不实现，只记录为残余风险。

风险视角挑战：入口治理延期后，长期数据库会积累历史 alias。处理结果：接受短期风险，因为 SQLite alias 成本低且当前目标是防串线；当入口列表开始难以理解或查询明显变慢时，开启后续治理任务。
