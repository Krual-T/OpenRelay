# Verification

## Required Commands
- `uv run python .codex/skills/openharness/scripts/openharness.py check-designs`
- `uv run python .codex/skills/openharness/scripts/openharness.py bootstrap --all`

## Expected Outcomes
- The new package validates under the current harness protocol.
- The package clearly captures the expanded scope: docs-root migration, legacy design migration, enforcement, and anti-drift.
- Historical package-maturation debt is tracked explicitly outside OR-016.

## Latest Result
- 2026-03-19: archived package moved from `docs/designs/harness-completion/` to `docs/archived/designs/harness-completion/` so completed design work no longer occupies the active design root.
- 2026-03-19: package status changed from `landed` to `archived` after confirming the task is complete and should remain as historical harness evidence instead of an active design package.
- 2026-03-19: `uv run python .codex/skills/openharness/scripts/openharness.py check-designs` passed after creating this package.
- 2026-03-19: `uv run python .codex/skills/openharness/scripts/openharness.py bootstrap --all` passed and listed `OR-016` plus `OR-015`.
- 2026-03-19: `uv run pytest .codex/skills/openharness/tests/test_openharness.py` passed after switching the manifest, scaffolding expectations, and discovery root to `docs/designs/`.
- 2026-03-19: `uv run python .codex/skills/openharness/scripts/openharness.py check-designs` passed again after moving both existing packages into `docs/designs/`.
- 2026-03-19: `uv run python .codex/skills/openharness/scripts/openharness.py bootstrap --all` reported `/home/Shaokun.Tang/Projects/openrelay/docs/designs` as the canonical design root.
- 2026-03-19: `uv run pytest .codex/skills/openharness/tests/test_openharness.py` passed after scaffolding packages for `OR-007`, `OR-009`, and `OR-010` through `OR-014`.
- 2026-03-19: `uv run python .codex/skills/openharness/scripts/openharness.py check-designs` and `uv run python .codex/skills/openharness/scripts/openharness.py bootstrap --all` passed with 9 design packages discovered under `docs/designs/`.
- 2026-03-19: legacy standalone design notes were moved under `docs/archived/legacy/`, `docs/TaskBoard.md` was removed, and `OR-017` was created to track remaining package-maturation debt.
- 2026-03-19: `uv run pytest .codex/skills/openharness/tests/test_openharness.py` passed after adding strong validation for status-flow and referenced-path errors.
- 2026-03-19: `uv run python .codex/skills/openharness/scripts/openharness.py check-designs` and `uv run python .codex/skills/openharness/scripts/openharness.py bootstrap --all` passed with 10 design packages discovered under `docs/designs/`.
- 2026-03-19: `uv run pytest .codex/skills/openharness/tests/test_openharness.py` passed after vendoring repository skills into `.codex/skills/`, removing the wrong-root plan artifact under the legacy docs root, and switching the harness test from symlink enforcement to local-skill enforcement.
- 2026-03-19: `uv run python .codex/skills/openharness/scripts/openharness.py check-designs` passed after updating repository-local planning and brainstorming skills to default to `docs/designs/<task>/` instead of the legacy docs root.
- 2026-03-19: `uv run pytest .codex/skills/openharness/tests/test_openharness.py` passed again after collapsing harness discovery, validation, scaffolding, and verify entrypoints into the single CLI `.codex/skills/openharness/scripts/openharness.py`.
- 2026-03-19: `uv run python .codex/skills/openharness/scripts/openharness.py check-designs` and `uv run python .codex/skills/openharness/scripts/openharness.py bootstrap --all` also passed after the single-CLI refactor.
- 2026-03-19: `uv run python .codex/skills/openharness/scripts/openharness.py check-designs` passed after consolidating the local entry-skill contract into `.codex/skills/openharness/SKILL.md` and `.codex/skills/openharness/references/skill-hub.md`.
- 2026-03-19: `uv run pytest .codex/skills/openharness/tests/test_openharness.py` passed with 13 tests after adding explicit assertions that `openharness` is the repository entry skill and that `skill-hub.md` forbids a parallel local entry layer.
- 2026-03-19: `uv run python .codex/skills/openharness/scripts/openharness.py check-designs` passed after updating `AGENTS.md` so the repo-level workflow instructions route skill usage through `openharness` first.
- 2026-03-19: `uv run pytest .codex/skills/openharness/tests/test_openharness.py` passed with 14 tests after adding an `AGENTS.md` contract check for repo-level skill routing through `openharness`.
- 2026-03-19: a repository-wide Python scan for the legacy brand token and its former entry-skill alias returned no matches after removing legacy entry-layer names from the local harness skill, skill hub, regression tests, and package notes.
- 2026-03-19: `uv run python .codex/skills/openharness/scripts/openharness.py check-designs` passed again after rewriting local harness wording to remove legacy entry-layer references.
- 2026-03-19: `uv run pytest .codex/skills/openharness/tests/test_openharness.py` passed with 14 tests after replacing the old-name assertions with zero-residue checks that still guard against reintroducing legacy terminology.
