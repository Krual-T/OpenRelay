# Evidence

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Residual Risks
- 飞书官方 CLI / 官方调试工具的真实能力尚未确认。
- 功能清单和验证矩阵尚未落成独立文件。
- 真实飞书手动触发后的 trace 验证样例尚未采集。

## Manual Steps
- 后续需要人工在飞书触发至少一条测试消息或卡片动作，并用本地 trace 查询验证链路。

## Files
- `docs/task-packages/feature-inventory-runtime-verification/README.md`
- `docs/task-packages/feature-inventory-runtime-verification/STATUS.yaml`
- `docs/task-packages/feature-inventory-runtime-verification/01-requirements.md`
- `docs/task-packages/feature-inventory-runtime-verification/02-overview-design.md`
- `docs/task-packages/feature-inventory-runtime-verification/03-detailed-design.md`
- `docs/task-packages/feature-inventory-runtime-verification/04-verification.md`
- `docs/task-packages/feature-inventory-runtime-verification/05-evidence.md`

## Commands
- `openharness new-task feature-inventory-runtime-verification --task-id OR-015 --title "Feature Inventory And Runtime Verification" --summary "Map user-visible features to real runtime verification evidence." --owner codex --status proposed`
- `openharness check-tasks` (`final verification command`)

## Artifact Paths
- 无独立验证产物。

## Follow-ups
- 调研飞书官方 CLI 或官方调试工具是否能辅助观测消息、卡片更新和流式 UI。
- 建立功能清单与验证矩阵。
- 设计“用户在飞书触发，我用本地 trace 验证”的标准流程。
