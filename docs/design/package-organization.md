# Package Organization

更新时间：2026-03-14

## 目标

把核心领域从顶层平铺模块收敛到稳定包结构：

- `openrelay.core`
- `openrelay.storage`
- `openrelay.feishu`
- `openrelay.runtime`
- `openrelay.session`
- `openrelay.backends`

## 调整原则

- 包级 `__init__.py` 作为稳定入口，对外统一导出主要能力。
- 不保留旧的顶层同名模块，避免长期双轨。
- 相关子模块就近归类，减少 `src/openrelay/` 根层继续膨胀。

## 当前结果

- `config.py`、`models.py`、`release.py` 从 `src/openrelay/` 根层收敛到 `openrelay.core`
- `state.py` 从 `src/openrelay/` 根层收敛到 `openrelay.storage`
- `openrelay.core` 现在承载配置、核心类型、发布通道与工作区语义
- `openrelay.storage` 现在承载 SQLite 持久化、schema 初始化与本地状态读写
- `runtime.py`、`runtime_commands.py`、`runtime_live.py` 与 runtime 交互模块收敛到 `openrelay.runtime`
- `follow_up.py`、`help_renderer.py`、`panel_card.py`、`render.py`、`runtime/execution.py`、`runtime/turn.py` 继续收敛到 `openrelay.runtime`
- `session_browser.py`、`session_ux.py`、`session_list_card.py`、`session_scope`、`session/lifecycle.py` 收敛到 `openrelay.session`
- `feishu_reply_card.py`、`streaming_card.py`、`feishu_ws.py` 继续收敛到 `openrelay.feishu`
- `card_actions.py`、`card_theme.py`、`typing.py` 收敛到 `openrelay.feishu`，其中卡片协议与主题进一步归类到 `openrelay.feishu.cards`
- `openrelay.feishu` 现在统一承载消息解析、发送、事件分发、卡片构建、流式卡片会话与 websocket 客户端
- `openrelay.runtime` 现在统一承载运行时主流程、命令路由、补充消息合并、帮助/面板视图、运行中渲染与进程控制
- `openrelay.backends` 保持 backend adapter / registry 的稳定边界，不再让 provider 细节渗回根层

## 边界补充

- `openrelay.session` 负责“会话是什么、怎么选、怎么展示”。
- `openrelay.runtime` 负责“消息到了之后怎么编排执行”。
- `openrelay.core` 负责跨包共享的稳定语义，例如 `SessionRecord`、release channel、workspace 规则。

因此：
- 会话装载、占位控制会话复用、top-level 到 thread 的会话继承，应该放在 `openrelay.session`。
- `/restart` 对应的 systemd / 进程控制属于 runtime 基础设施，应保留在 `openrelay.runtime`，但不应继续塞在 `RuntimeOrchestrator` 这个消息编排类里，更不该再被误叫成 agent。
- backend turn 生命周期、流式回复状态、active run / follow-up 队列属于 runtime 执行层，应拆到独立协作者，而不是继续堆在入口类里。
