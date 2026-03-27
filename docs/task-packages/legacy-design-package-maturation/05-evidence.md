# Evidence

## Files
- `AGENTS.md`
- `docs/task-packages/legacy-design-package-maturation/README.md`
- `docs/task-packages/legacy-design-package-maturation/STATUS.yaml`
- `docs/task-packages/legacy-design-package-maturation/01-requirements.md`
- `docs/task-packages/legacy-design-package-maturation/02-overview-design.md`
- `docs/task-packages/legacy-design-package-maturation/03-detailed-design.md`
- `docs/task-packages/legacy-design-package-maturation/04-verification.md`
- `docs/task-packages/legacy-design-package-maturation/05-evidence.md`
- `docs/task-packages/*`
- `docs/archived/task-packages/*`

## Commands
- `openharness bootstrap`
- `openharness check-tasks` (`final verification command`)

## Follow-ups
- Start the next detailed-design pass in one target package at a time.
- 持续清理 archived package 的历史占位内容，但这已不再阻塞当前 active package 通过 `openharness check-tasks`。
