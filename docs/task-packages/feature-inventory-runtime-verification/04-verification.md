# Verification

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Verification Path
- Planned Path:
  - 本包建档阶段先执行 `openharness check-tasks`，确认 task package 结构符合仓库协议。
  - 后续探索阶段需要补充官方飞书工具调研证据和至少一条真实飞书 trace 验证证据。
- Executed Path:
  - 已执行 `openharness check-tasks`。
- Path Notes:
  - 当前只验证 task package 结构合法；功能清单、官方工具调研和真实运行验收仍属于后续阶段。

只有当实现已经完成到足以采集新证据时，才进入 `verifying`。
如果实现仍然延期到后续轮次，就不要使用 `archived`。

## Required Commands
- `openharness check-tasks`

## Expected Outcomes
- `openharness check-tasks` 应确认新增 task package 结构合法。
- 后续真实运行验证应能从一条飞书测试消息追踪到 openrelay 的 ingress、命令或 turn、reply 证据。

## Traceability
- `01-requirements.md` 定义必须交付功能清单、验证矩阵、官方飞书工具调研和手动触发验证工作流。
- `02-overview-design.md` 定义三层结构和主验证流。
- 当前缺口是详细设计尚未完成，真实运行证据尚未采集。

## Risk Acceptance
- 接受当前只完成 task package 建档，不宣称官方 CLI 能力或真实验证闭环已经成立。
- 当进入探索阶段时，如果官方工具不能覆盖 UI 观测，应明确降级为人工 UI 观察加本地 trace 判断。

## Latest Result
- 2026-05-04：`openharness check-tasks` 通过，输出确认验证了 7 个 task package。
- Latest Artifact:
