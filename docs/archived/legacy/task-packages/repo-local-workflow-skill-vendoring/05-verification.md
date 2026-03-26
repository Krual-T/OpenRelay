# Verification

## Required Commands
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks --repo .`
- `uv run --extra dev pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py -q`

## Expected Outcomes
- OR-020 validates as a complete design package.
- Harness tests verify the new repo-local generic workflow skill locations.

## Latest Result
- `2026-03-20`: `check-tasks` passed for 13 design packages.
- `2026-03-20`: repo-local harness tests passed with `21 passed`.
- `2026-03-20`: package archived under `docs/archived/legacy/task-packages/repo-local-workflow-skill-vendoring/`, `check-tasks` re-passed, and default `bootstrap` no longer lists OR-020 as active.
