# Runtime Agent Boundary Refactor

更新时间：2026-03-15

## 问题

当前 runtime 已经做过一轮拆分，但边界仍不稳定：

- `RuntimeOrchestrator` 仍然混有 panel / session-list 展示发送与 reply route 细节。
- `RuntimeCommandRouter` 同时承担命令解析、domain action 和文案拼装。
- `SessionUX` 同时承担 session 展示、workspace 路径规则、directory shortcut 规则。
- `BackendTurnSession` 同时承担 turn 生命周期和 Feishu streaming UI 细节。

这会导致两个问题：

- runtime 入口虽然文件变小了，但仍然持续吸收不属于编排层的职责。
- 已经拆出去的模块里仍有“平移出来的内部方法”，没有形成稳定领域边界。

## 目标边界

### runtime 应保留

- 顶层消息编排：鉴权、去重、分流、异常边界
- 执行协调：active run、串行锁、follow-up 队列、stop/cancel
- 单次 turn 生命周期：backend 调用、session 持久化、turn 级交互接入
- 跨模块装配：把 backend / session / release / feishu 协作者接起来

### runtime 不应继续保留

- panel / help / session-list 的 view-model 和 fallback 文案拼装
- reply route、card update target、force-new-message 等渠道发送策略
- workspace 路径解析与目录 shortcut 策略
- release / session 变更的业务细节

## 目标模块

- `runtime.orchestrator`
  只保留 dispatch、命令与 turn 分流、顶层装配
- `runtime.execution`
  active run、串行化、live-input、follow-up
- `runtime.turn`
  backend turn 生命周期
- `runtime.replying`
  reply route、card update target、command reply policy
- `runtime.presenters.help`
  help text/card
- `runtime.presenters.panel`
  panel/session-list card + fallback text + send
- `runtime.commands`
  parse + dispatch，不直接持有大块展示细节
- `session.workspace`
  cwd resolve / format、workspace root 规则
- `session.shortcuts`
  shortcut 聚合、过滤、解析、展示入口数据
- `session.presentation`
  session title / preview / meta / context / usage 等展示逻辑

## 分阶段方案

### Phase 1

- 把 `SessionUX` 中的 workspace / shortcut 逻辑下沉到 `session.workspace` 与 `session.shortcuts`
- 保留 `SessionUX` 薄委托，减少一轮内的大面积兼容改动

完成标志：

- `/cwd`、`/shortcut`、help/panel 的目录入口不再依赖 `SessionUX` 承载路径规则

### Phase 2

- 把 orchestrator 里的 `/panel` 与 `/resume list` 发送逻辑抽成独立 presenter / sender
- orchestrator 只负责调用，不再拼装 panel data 和 fallback text

完成标志：

- `RuntimeOrchestrator` 不再持有 panel/session-list 的大块 helper

### Phase 3

- 把 reply route 和 command-card update policy 从 orchestrator 抽到独立协作者
- 统一文本回复、命令回复、卡片更新的发送策略

完成标志：

- orchestrator 不再直接决定大部分 Feishu reply route 细节

### Phase 4

- 收缩 `RuntimeCommandRouter`，把 session/release/system 命令细节继续下沉
- router 主要保留 parse + dispatch

### Phase 5

- 把 `BackendTurnSession` 里的 streaming / typing bridge 拆到独立协作者
- turn 只保留 backend 生命周期和 turn 级状态推进

## 本轮实施

本轮优先完成 Phase 1 和 Phase 2：

- Phase 1 在 session 域先建立稳定边界
- Phase 2 直接减轻 orchestrator，避免继续把 panel 逻辑堆回入口类

## 取舍

- 本轮不追求一次性删除所有兼容 facade
- 先建立清晰模块，再逐步删除 `SessionUX` / `RuntimeOrchestrator` 中残留的转发方法
- 优先缩短主路径，而不是先做“理论上更完整”的抽象
