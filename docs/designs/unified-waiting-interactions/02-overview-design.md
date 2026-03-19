# Overview Design

## System Boundary
本任务当前先把历史遗留任务描述收敛成正式 package。范围以内只定义问题边界、目标体验和高层模块关系；具体实现与迁移细节留到下一轮详细设计。

## Proposed Structure
- `01-requirements.md` 固定任务目标、当前关注和关闭条件。
- `02-overview-design.md` 固定产品边界和主交互方向。
- `03-detailed-design.md` 记录下一轮需要细化的文件级落点和验证计划。

## Key Flows
- 用户问题通过飞书线程进入当前会话。
- 系统需要把当前高频状态/交互收敛成更稳定、更可理解的主路径。
- 设计完成后，后续实现应优先落在：
  - src/openrelay/runtime/
  - src/openrelay/feishu/

## Trade-offs
- 先 formalize package 能让任务进入 harness 主路径，但不会自动解决需求细节不足的问题。
- 本轮优先解决事实源收敛，后续再做实现级设计。
