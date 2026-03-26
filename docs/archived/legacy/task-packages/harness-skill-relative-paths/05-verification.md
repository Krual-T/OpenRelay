# Verification

## Required Commands
- `.agents/skills/openharness/using-openharness/scripts/openharness.py bootstrap --repo .`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks --repo .`
- `! rg -n "\.codex/skills/openharness|uv run python .*openharness\.py" AGENTS.md docs .project-memory -S -g '!docs/archived/legacy/task-packages/harness-skill-relative-paths/**' -g '!docs/archived/legacy/task-packages/harness-skill-relative-paths/**'`

## Expected Outcomes
- The harness CLI still discovers active design packages from the repository root.
- Design-package validation passes after the path migration.
- No repository protocol files still reference the old `.codex` harness path or the old `uv run python ...openharness.py` form.

## Latest Result
- 2026-03-19: `.agents/skills/openharness/using-openharness/scripts/openharness.py bootstrap --repo .` passed and listed the active design packages from `docs/task-packages/`.
- 2026-03-19: `.agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks --repo .` passed after refreshing the archived harness package evidence paths.
- 2026-03-19: `.agents/skills/openharness/using-openharness/scripts/openharness.py verify OR-018 --repo .` passed, including the negative grep guard for stale `.codex` references.
