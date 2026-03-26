# Evidence

## Files
- `AGENTS.md`
- `docs/task-packages/legacy-design-package-maturation/README.md`
- `docs/task-packages/legacy-design-package-maturation/STATUS.yaml`
- `docs/task-packages/legacy-design-package-maturation/01-requirements.md`
- `docs/task-packages/legacy-design-package-maturation/02-overview-design.md`
- `docs/task-packages/legacy-design-package-maturation/03-detailed-design.md`
- `docs/task-packages/legacy-design-package-maturation/05-verification.md`
- `docs/task-packages/legacy-design-package-maturation/06-evidence.md`
- `docs/task-packages/*`
- `docs/archived/task-packages/*`

## Commands
- `.agents/skills/openharness/using-openharness/scripts/openharness.py new-design legacy-design-package-maturation OR-017 "Legacy Design Package Maturation" --owner codex --summary "Track historical packages that were scaffolded from legacy task notes and still need implementation-grade design completion."`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py bootstrap`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks`

## Follow-ups
- Start the next detailed-design pass in one target package at a time.
- Clean up archived packages that still contain placeholder sections or stale skill/template references so `check-tasks` can pass repository-wide again.
