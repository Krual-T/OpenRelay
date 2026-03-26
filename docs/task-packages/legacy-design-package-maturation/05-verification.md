# Verification

## Required Commands
- `.agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks`

## Expected Outcomes
- The remaining historical package-maturation work has a dedicated package.

## Latest Result
- 2026-03-19: package scaffolded as the explicit follow-up to OR-016.
- 2026-03-26: repository package roots were migrated from `docs/designs` / `docs/archived/designs` to `docs/task-packages` / `docs/archived/task-packages`, and `AGENTS.md` verification guidance was aligned from `check-designs` to `check-tasks`.
- 2026-03-26: `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py bootstrap` passed and reported `docs/task-packages` as the active package root.
- 2026-03-26: `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks` still fails, but the remaining failures are archived-package placeholder sections and stale referenced skill/template paths rather than the active-root migration itself.
