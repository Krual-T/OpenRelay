# Requirements

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Goal
明确 openrelay 中 `/resume` 的会话生命周期意图：用户恢复一个后端会话后，应能清楚知道这个恢复入口是否持续有效、在哪里继续聊天、多个恢复入口之间是否相互独立，以及长期积累大量入口时如何管理。

单一成功指标：维护者能够用一段明确需求说明回答“我现在能同时在几个恢复会话里聊天、是否需要每次发消息前重新 resume、恢复无数条后怎么办”。

## Problem Statement
真实飞书运行中已经暴露 `/resume` 会话错乱：用户连续恢复不同后端会话后，多个飞书回复 thread 可能被绑定到同一个当前会话或被后续恢复覆盖。当前痛点不是单个 bug，而是产品语义缺失：`/resume` 是一次性切换、持久入口、临时缓存，还是某种可关闭的聊天窗口，目前没有被明确写成约定。

目标用户是通过飞书与 openrelay 对话的维护者。核心场景是用户从 `/resume` 卡片恢复多个历史后端会话，并希望在多个飞书 thread 中并行或交替继续上下文。

现在需要做，是因为继续修补单个串会话 bug 会把隐含设计散落到代码里；先明确意图、待讨论问题和待探索事实，才能避免后续实现反复改变语义。

## Required Outcomes
1. 形成 `/resume` 生命周期需求说明。
   - `acceptance criteria`：说明必须明确持续性、入口数量、入口与后端会话关系、失效或清理边界。
2. 明确需要讨论的问题。
   - `acceptance criteria`：列出仍属于产品语义或使用体验选择的问题，不把它们提前写成结论。
3. 明确需要探索的问题。
   - `acceptance criteria`：列出必须通过代码、数据库、飞书事件字段或真实运行 trace 才能确认的问题。

## Requirements Closure
本轮将 `/resume` 定义为“打开一个可继续回复的恢复入口”，不是切换顶层默认会话。

- `/resume` 成功后，用户应回复成功消息对应的子 thread 继续该后端会话；顶层普通消息继续保持新对话语义。
- 每次成功连接都可以创建一个独立本地会话和一个独立可回复入口；同一个后端 `native_session_id` 被多次连接时，也先按多个入口处理，避免复用入口时误伤历史 thread。
- 恢复入口是持久入口：只要飞书消息和本地 SQLite 绑定仍存在，后续回复就应继续命中同一个本地会话。
- 本轮不做用户可见的关闭、归档、清理入口；大量入口治理作为后续产品能力，不阻塞当前生命周期语义收敛。
- 同一个 `native_session_id` 的并发 backend turn 默认不声明安全；实施阶段需要至少用本地锁策略阻止同一后端会话被并发运行，或把这个风险显式暴露为未覆盖能力。

## Needs Discussion
- 已关闭：`/resume` 成功后按“长期聊天入口”处理，不按“切换顶层默认会话”处理。
- 已关闭：同一个后端会话多次 resume 时，本轮优先创建多个独立入口；复用提示和入口去重延期。
- 已关闭：用户通过成功回复文案看到 `session_id`、`cwd` 和“回复本条消息继续”的入口说明。
- 已关闭：顶层普通消息与恢复入口始终隔离。
- 延期：入口数量上限、隐藏、归档、关闭和清理入口不进入本轮实现。

## Needs Exploration
- 已确认：飞书 card action 事件可提供 `context.open_message_id`、`operator.open_id`、`action.value`、`action.form_value`、`action.input_value` 等字段；同一张卡片的不同连接按钮可能共享原卡片 `open_message_id`，因此不能只用卡片消息 id 区分恢复入口。
- 已确认：`session_key_aliases` 可以把成功回复消息 id 绑定到新建本地会话，`session_pointers` 记录 scope 到 session 的当前指针，`sessions` 保留本地会话记录，`relay_session_bindings` 保留 relay 到 backend attachment。
- 已确认：当前 execution key 默认按 `session.session_id` 串行；多个本地会话绑定同一个 `native_session_id` 时，现有锁不能天然阻止同一后端会话并发。
- 待实施验证：`/status` 和 trace 需要能让维护者看到成功回复 thread、`relay_session_id`、`native_session_id` 的对应关系。
- 延期：大量历史绑定的自动清理成本需要后续入口治理任务再量化。

## Non-Goals
- 本轮不实现新的缓存、清理或并发控制机制。
- 本轮不删除现有历史会话或迁移真实运行数据库。
- 本轮不把某个具体方案写成最终设计。
- `counterexample`：仅修复某一次真实测试里的错误绑定，不等于完成本包；本包关注的是长期语义和生命周期边界。

## Constraints
- 必须兼容飞书真实消息与 card action 事件字段，而不是只依赖测试构造字段。
- 不应破坏已有普通消息、顶层命令和子 thread 回复的基本路由语义。
- 不应把 Codex 原生会话删除或修改作为默认清理手段。
- `cost cap`：需求澄清阶段只做文档与必要事实探索，不进行大规模实现。
