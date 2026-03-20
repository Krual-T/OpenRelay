# Verification

## Required Commands
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-designs --repo .`
- `uv run --extra dev pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py -q`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py verify OR-019 --repo .`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-completion OR-019 --repo .`

## Expected Outcomes
- The repo-local OpenHarness assets validate against the design-package protocol.
- The repo-local harness tests cover routing and completion-check behavior and pass.
- OR-019 can move into `verifying` only after package evidence and status are updated.

## Latest Result
- `2026-03-20`: `check-designs` passed for 12 design packages.
- `2026-03-20`: repo-local harness tests passed with `20 passed`.
- `2026-03-20`: `verify OR-019` passed and re-ran the package-required commands successfully.
- `2026-03-20`: `check-completion OR-019` passed.
