# Implementation Plan

## Applicability
- This task was small enough to execute directly after confirming the path model.

## Execution Slices
- Update `using-openharness` to use relative internal paths and `.agents`-aware discovery.
- Normalize repository protocol and design-package references.
- Verify that the harness CLI still boots and validates design packages.

## Verification Gates
- `.agents/skills/openharness/using-openharness/scripts/openharness.py bootstrap --repo .`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py check-designs --repo .`
- `! rg -n "\.codex/skills/openharness|uv run python .*openharness\.py" AGENTS.md docs .project-memory -S -g '!docs/archived/designs/harness-skill-relative-paths/**'`

## Commit Plan
- Keep the repository protocol cleanup in one focused commit after verification passes.
