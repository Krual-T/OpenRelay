# Runtime Modularization

更新时间：2026-03-10

## 背景

当前 `openrelay` 已经有基础分层：配置、状态存储、后端适配、飞书接入、卡片渲染、会话 UX 都有独立文件。

但核心编排层仍然过重：`src/openrelay/runtime.py` 同时承担消息分发、命令路由、帮助文案构造、面板发送、发布通道切换、进程重启和部分会话交互逻辑。随着 `/help` 卡片化、`/resume` 卡片分页排序等需求继续进入，这个文件会继续膨胀。

问题不在于“文件数量不够多”，而在于模块边界还不稳定：
- `AgentRuntime` 既做调度，又做展示。
- `SessionUX` 同时承担查询、恢复、排序、格式化。
- 新交互需求正在把更多展示和命令分支继续塞回 runtime 主文件。

## 目标

本轮重构不追求一次性引入复杂框架，而是先把边界收敛到更稳定的方向：

- `runtime` 只保留编排、状态推进和对外协作。
- 帮助文案、卡片文案、会话列表展示等“展示逻辑”逐步抽离成独立模块。
- 会话列表的查询 / 恢复决策，与展示格式化逐步拆层。
- 为后续 `/help` 卡片化、`/resume` 分页排序提供清晰落点。

## 不做的事

为了避免过度抽象，本轮明确不做下面这些事：

- 不引入插件式命令框架。
- 不同时改写 `StateStore` 和 `FeishuMessenger` 的整体模型。
- 不为了“未来灵活”先造一层过重的抽象基类。
- 不在没有明确收益的情况下把所有命令一次性拆散。

## 分阶段方案

### Phase 1：先抽纯展示逻辑

优先把不直接驱动状态流转、主要负责拼装用户可见内容的逻辑从 `AgentRuntime` 拆出去。

首选切口：
- `/help` 文本构造 -> 独立 `HelpRenderer`
- 后续 `/help` 卡片构造 -> 可继续沿同一模块扩展

原因：
- 输入输出边界清晰
- 依赖面小
- 容易通过已有测试回归验证
- 不会破坏运行时主路径

### Phase 2：收敛会话浏览层

把 `SessionUX` 中混杂的职责拆成两层：
- 会话查询 / 合并 / 恢复决策
- 文本 / 卡片展示格式化

这一层是 `/resume` 卡片化、分页、排序的基础，不应继续靠 `dict[str, object]` 和零散字段拼接支撑。

### Phase 3：收敛命令路由层

当 `/help`、`/panel`、`/resume` 都有稳定展示模块后，再继续把 `_handle_command` 中的命令分支收敛成更清楚的命令处理层。

目标不是“所有命令都插件化”，而是让 runtime 主文件不再承担所有命令细节。

### Phase 4：再考虑飞书适配层细分

如果后续卡片交互继续扩展，再考虑把 `feishu.py` 里的 parser / messenger / dispatcher 进一步拆开。

这一步应晚于 runtime 与 session 边界收敛，否则只会把复杂度平移。

## 当前进展

已完成 Phase 1：
- 新增 `src/openrelay/help_renderer.py`
- 把 `/help` 文本构造从 `AgentRuntime` 移出
- `AgentRuntime` 只负责调用帮助渲染器
- 增加针对帮助渲染器的独立测试

本轮继续推进 Phase 2 与 Phase 3：
- 新增 `src/openrelay/session_browser.py`
- 把会话列表查询和恢复决策从 `SessionUX` 移出
- `SessionUX` 收敛为会话列表文本 / 面板展示格式化
- 为 `/resume` 卡片化和分页排序保留稳定的数据入口与测试落点
- 新增 `src/openrelay/runtime_commands.py`
- 把 `_handle_command` 的主分支树从 `AgentRuntime` 收敛到独立命令路由层
- `runtime.py` 只保留命令相关协作入口与少量状态密切相关的 helper
- 2026-03-15 新增 `src/openrelay/session/lifecycle.py`，把会话装载 / 占位会话复用策略移回 `openrelay.session`
- 2026-03-15 新增 `src/openrelay/runtime/restart.py`，把 systemd / 进程重启控制从 `AgentRuntime` 分离为 runtime 内部协作者
- `AgentRuntime` 进一步收敛为消息编排器，避免继续混入会话域策略和进程控制细节
- 2026-03-15 新增 `src/openrelay/runtime/turn.py`，把 backend turn 生命周期、交互控制、流式回复状态从 `AgentRuntime` 移出
- 2026-03-15 新增 `src/openrelay/runtime/execution.py`，把 active run、串行锁和 follow-up 队列从 `AgentRuntime` 移到执行协调器
- `AgentRuntime` 现在主要保留 dispatch、命令分流、session 解析委托与顶层异常边界

## 预期结果

完成这一轮后，收益主要有四点：
- `runtime.py` 直接减重，帮助逻辑和主命令分支不再继续堆在主编排类里。
- `/help` 的文本版与后续卡片版有共同落点。
- 会话浏览已经有稳定的数据入口，可继续承接 `/resume` 与 `/panel` 的分页、排序和卡片交互。
- 后续继续拆 `/resume`、`/panel` 或命令细节时，可以沿同样模式推进，而不是再次回到“大文件里塞新分支”的路径。
