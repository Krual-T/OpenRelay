# Evidence

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Residual Risks
- 需求尚未收敛；所有设计选择仍待讨论或探索。

## Manual Steps
- 无。

## Files
- `docs/task-packages/resume-binding-lifecycle/README.md`
- `docs/task-packages/resume-binding-lifecycle/STATUS.yaml`
- `docs/task-packages/resume-binding-lifecycle/01-requirements.md`
- `docs/task-packages/resume-binding-lifecycle/02-overview-design.md`
- `docs/task-packages/resume-binding-lifecycle/03-detailed-design.md`
- `docs/task-packages/resume-binding-lifecycle/04-verification.md`
- `docs/task-packages/resume-binding-lifecycle/05-evidence.md`

## Commands
- `openharness new-task resume-binding-lifecycle --task-id OR-018 --title "Resume Binding Lifecycle" --summary "Clarify how resumed backend sessions map to persistent Feishu conversation entrypoints." --owner codex --status proposed`
- `openharness check-tasks` (`final verification command`)

## Artifact Paths
- 无。

## Follow-ups
- 讨论 `Needs Discussion` 中的问题。
- 探索 `Needs Exploration` 中的代码、数据库和真实飞书事件事实。
