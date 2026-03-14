# Package Organization

更新时间：2026-03-14

## 目标

把核心领域从顶层平铺模块收敛到稳定包结构：

- `openrelay.feishu`
- `openrelay.runtime`
- `openrelay.session`

## 调整原则

- 包级 `__init__.py` 作为稳定入口，对外统一导出主要能力。
- 不保留旧的顶层同名模块，避免长期双轨。
- 相关子模块就近归类，减少 `src/openrelay/` 根层继续膨胀。

## 当前结果

- `runtime.py`、`runtime_commands.py`、`runtime_live.py` 与 runtime 交互模块收敛到 `openrelay.runtime`
- `session_browser.py`、`session_ux.py`、`session_list_card.py`、`session_scope` 收敛到 `openrelay.session`
- `feishu_reply_card.py`、`streaming_card.py`、`feishu_ws.py` 继续收敛到 `openrelay.feishu`
- `openrelay.feishu` 现在统一承载消息解析、发送、事件分发、卡片构建、流式卡片会话与 websocket 客户端
