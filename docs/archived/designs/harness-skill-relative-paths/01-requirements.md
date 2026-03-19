# Requirements

## Goal
Make harness path references resilient to the `.agents/skills/openharness/<skill>/` layout without falling back to hardcoded `.codex` paths or `uv run python ...` wrappers.

## Problem Statement
The repository still treated the old `.codex/skills/openharness/...` path as the canonical harness location. After the migration to `.agents/skills/openharness/`, these references became wrong in three different ways: the root path changed, `openharness` is now a skills collection rather than one skill directory, and the old command examples encoded a specific Python launcher instead of the actual relative script path.

## Required Outcomes
1. `using-openharness` uses relative `scripts/`, `references/`, and `tests/` paths inside the skill itself.
2. The harness CLI resolves its manifest and templates from the `.agents/skills/openharness/using-openharness/` layout or from its own neighboring files instead of assuming `.codex`.
3. `AGENTS.md`, active design packages, archived harness packages, and memory no longer point at `.codex/skills/openharness/...` or `uv run python ...openharness.py`.
4. Repository-level runnable commands point at `.agents/skills/openharness/using-openharness/scripts/openharness.py`.

## Non-Goals
- Adding a new repository wrapper such as `scripts/openharness`.
- Changing the design-package protocol beyond path and command normalization.
- Refactoring unrelated skills such as `project-memory`.

## Constraints
- `.agents/skills/openharness` must remain a skills root containing multiple child skills.
- `using-openharness` must keep owning its own `scripts/`, `references/`, and `tests/` assets.
- Verification commands stored in `STATUS.yaml` must remain runnable from the repository root.
