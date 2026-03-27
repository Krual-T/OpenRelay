# Overview Design

## System Boundary
本轮范围聚焦在“移除用户可见的 release channel 切换语义”，把目录上下文主路径统一收敛到 workspace 选择与 shortcut 跳转。底层持久化兼容暂时保留，不在这一轮演变成数据库清理任务。

## Proposed Structure
- `runtime/command_router.py` 不再注册 `/main`、`/stable`、`/develop`。
- `runtime/help.py` 不再向用户暴露 release channel 切换命令。
- `presentation/runtime_status.py`、`presentation/panel.py`、`presentation/session.py` 不再把 channel 作为主路径状态事实展示。

## Key Flows
- 用户问题通过飞书线程进入当前会话。
- 用户若要换执行位置，只通过 `/workspace` 或 `/shortcut` 进入目标目录。
- 用户查看当前现场时，只看到目录、模型、sandbox、backend thread，不再看到 `main/develop` channel。
- 设计完成后，后续实现应优先落在：
  - `src/openrelay/runtime/command_router.py`
  - `src/openrelay/runtime/help.py`
  - `src/openrelay/presentation/runtime_status.py`
  - `src/openrelay/presentation/panel.py`
  - `src/openrelay/presentation/session.py`

## Trade-offs
- 直接删除底层 release 模型会更彻底，但会把这一轮扩大成存储迁移与兼容清理。
- 先移除用户入口和展示语义，可以先把主路径收敛正确，再决定后续是否删掉残余内部字段。
