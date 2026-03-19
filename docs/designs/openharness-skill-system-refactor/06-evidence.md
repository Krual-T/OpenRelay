# Evidence

## Files
- `docs/designs/openharness-skill-system-refactor/README.md`
- `docs/designs/openharness-skill-system-refactor/STATUS.yaml`
- `docs/designs/openharness-skill-system-refactor/01-requirements.md`
- `docs/designs/openharness-skill-system-refactor/02-overview-design.md`
- `docs/designs/openharness-skill-system-refactor/03-detailed-design.md`
- `docs/designs/openharness-skill-system-refactor/05-verification.md`
- `docs/designs/openharness-skill-system-refactor/06-evidence.md`

## Commands
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py new-design openharness-skill-system-refactor OR-019 "OpenHarness Skill System Refactor" --owner codex --summary "Refactor OpenHarness into a protocol-first, skill-driven harness with workflow routing, completion gates, and research intake rules." --repo .`

## Follow-ups
- Write `04-implementation-plan.md` for OR-019 before touching harness behavior.
- Implement completion-checker support and the new routing and skill boundaries.
