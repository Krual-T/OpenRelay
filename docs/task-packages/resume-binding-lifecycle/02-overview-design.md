# Overview Design

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## System Boundary
本轮覆盖 `/resume` 恢复入口的产品语义、会话绑定边界、card action 成功回复入口、后续普通回复路由和验证面。

覆盖的仓库表面：

- `feishu/parsing.py`：只负责把 card action 的稳定字段转成 `IncomingMessage`，不在这里决定生命周期语义。
- `session/scope/resolver.py`：负责把显式 `session_key`、thread id、成功回复 message id 别名解析到稳定会话 scope。
- `runtime/command_handlers/runtime_session.py` 与 `runtime/command_services/runtime_session_commands.py`：负责 `/resume` 连接行为、独立 scope 生成、成功文案和本地会话创建。
- `runtime/reply_service.py` 与 `runtime/replying.py`：负责成功回复落到新的飞书消息，并把该回复的 message id 记成可继续入口。
- `storage` 与 `session/store.py`：保留 `sessions`、`session_pointers`、`session_key_aliases`、`relay_session_bindings` 的现有事实源职责。

不覆盖的表面：

- 不设计入口列表、关闭、归档、批量清理和容量上限。
- 不删除或迁移真实运行数据库里的旧会话。
- 不改变 Codex 原生会话存储，也不把 native session 当作可以由 openrelay 清理的对象。
- 不把所有飞书卡片交互统一重做；只约束 `/resume` 成功连接和后续回复。

## Proposed Structure
推荐结构是“成功回复消息即恢复入口”。

1. `/resume` 顶层命令只负责展示列表或直接连接；它不改变顶层普通消息的默认新对话语义。
2. `/resume` card action 点击后，根据 card action 事件和目标 `native_session_id` 生成独立恢复 scope，再创建新的本地 `SessionRecord`。
3. 成功回复以新的飞书消息发出；`RuntimeReplyService` 用 `alias_session_key` 把成功回复 message id 和 thread id 写入 `session_key_aliases`。
4. 用户回复成功消息时，普通消息解析先命中 root/thread alias，再加载对应本地 `relay_session_id`，从 `relay_session_bindings` 读取目标 `native_session_id`。
5. 顶层普通消息没有 root/thread alias，不参与恢复入口，仍按新的消息 scope 建立新对话。

关键边界：

- 飞书事件解析层只暴露字段，不推断“这次点击是不是一个新入口”。
- `/resume` 命令层拥有入口创建语义。
- session scope 层拥有“哪个飞书 message/thread 指向哪个本地会话”的事实。
- binding 层拥有“哪个本地会话连接哪个 backend native session”的事实。
- observability 层负责让维护者能从 trace 或 SQLite 查询复盘入口绑定。

## Key Flows
### Flow A: 顶层 `/resume`

用户在私聊顶层发送 `/resume`。系统按顶层 control scope 加载当前本地会话，并发送可交互会话列表卡片。此时不创建恢复入口。

### Flow B: 点击连接按钮

用户点击列表卡片中的连接按钮。Feishu card action 进入 `parse_card_action_event`，生成 `source_kind=card_action` 的 `IncomingMessage`，其中 `message_id` 与 `reply_to_message_id` 指向原卡片消息。命令层解析目标 `native_session_id`，用 `event_id/message_id + target_session_id` 生成独立恢复 scope，创建新本地会话并绑定目标后端会话。成功回复发成新的飞书消息，并把该成功回复的 message id 写成入口别名。

### Flow C: 回复成功消息继续

用户回复成功消息。普通消息事件带 root/thread/parent 信息。scope resolver 先查 `session_key_aliases`，找到 Flow B 写入的 alias，加载正确本地会话，再进入 backend turn。失败信号是 trace 里后续普通消息的 `session_key`、`relay_session_id` 或 `native_session_id` 与成功回复记录不一致。

### Flow D: 顶层普通消息隔离

用户不回复成功消息，而是在顶层直接发普通消息。消息没有恢复入口 alias，系统按顶层新消息 scope 创建或加载普通会话；这不是 `/resume` 的继续入口。

### Key Failure Modes

- 同一张卡片连续点击两个连接按钮，如果 scope 只依赖原卡片 `open_message_id`，第二次会覆盖第一次。
- 成功回复没有写 outbound alias，后续回复会退回顶层 scope 或错误 scope。
- 多个本地会话绑定同一个 `native_session_id` 时，按 `relay_session_id` 加锁会允许后端会话并发。
- `/status` 或 trace 缺少入口对应关系时，维护者只能从数据库多表手工推断。

降级方向：如果真实飞书事件字段不足以自动区分入口，则入口唯一性继续由本地生成的恢复 scope 和成功回复 message id 承担；如果同一 native session 并发被证明不安全，则先在执行层增加 native-session 级串行化，而不是回退到单入口覆盖模型。

## Stage Gates
- 已确定产品语义：`/resume` 打开持久恢复入口，成功回复子 thread 是继续位置，顶层普通消息隔离。
- 已确定边界：入口创建在 `/resume` 命令层，入口解析在 session scope 层，backend attachment 在 binding 层。
- 已确定关键失败模式：原卡片消息 id 复用、outbound alias 缺失、native session 并发、trace 不可判读。
- 已确定降级方向：入口唯一性依赖本地 scope 与成功回复别名；并发风险用执行层 native-session 锁收敛，不用覆盖旧入口。

## Trade-offs
- 方案 A：每次 `/resume` 成功都创建独立恢复入口。优点是最符合真实飞书 thread 使用方式，能支持多个历史会话并行或交替继续；代价是入口会累积，需要后续治理。采用。
- 方案 B：同一个 backend `native_session_id` 只复用一个入口。优点是入口数量少；代价是用户从旧成功回复继续时可能被新入口覆盖，且需要先设计入口查找和可见复用提示。拒绝，延期到入口治理任务。
- 方案 C：`/resume` 只切换顶层默认会话。优点是实现最短；代价是多个恢复会话无法并行，且与真实问题中“回复成功消息继续”的用户动作不一致。拒绝。

## Overview Reflection
架构视角挑战：每次 resume 都创建新本地会话，会不会让同一个后端会话出现多个 relay wrapper。处理结果：接受这个代价，因为它换来飞书入口隔离；但把 native-session 并发列为实施阶段硬约束。

产品视角挑战：入口持续有效但没有清理入口，会不会导致长期列表失控。处理结果：延期，原因是当前最危险的是串会话；清理入口需要单独设计可见列表、关闭语义和误删恢复路径。

测试视角挑战：只跑单元测试不能证明真实飞书 thread 字段稳定。处理结果：接受为验证约束；后续验证必须至少保留一条真实 card action 点击后的成功回复和后续回复 trace，无法自动采集时记录人工步骤与 SQLite 查询。
