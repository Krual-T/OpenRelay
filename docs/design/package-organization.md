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
- `feishu` 维持上一轮已经完成的包结构
