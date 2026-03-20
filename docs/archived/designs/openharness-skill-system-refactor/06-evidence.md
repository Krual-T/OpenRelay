# Evidence

## Files
- `.gitignore`
- `.agents/skills/openharness/using-openharness/SKILL.md`
- `.agents/skills/openharness/using-openharness/references/skill-hub.md`
- `.agents/skills/openharness/using-openharness/references/manifest.yaml`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py`
- `.agents/skills/openharness/using-openharness/tests/test_openharness.py`
- `.agents/skills/researching-solutions/SKILL.md`
- `.agents/skills/openharness/closing-design-package/SKILL.md`
- `.agents/skills/openharness/verification-before-completion/SKILL.md`
- `.agents/skills/openharness/project-memory/SKILL.md`
- `docs/archived/designs/openharness-skill-system-refactor/04-implementation-plan.md`
- `docs/archived/designs/openharness-skill-system-refactor/05-verification.md`
- `docs/archived/designs/openharness-skill-system-refactor/06-evidence.md`
- `docs/archived/designs/openharness-skill-system-refactor/STATUS.yaml`
- `.project-memory/facts/openharness_completion_contract.yaml`

## Commands
- `uv run --extra dev pytest -q`
- `uv run --extra dev pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py -q`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-designs --repo .`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py verify OR-019 --repo .`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-completion OR-019 --repo .`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py bootstrap --repo .`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py bootstrap --all --repo .`

## Follow-ups
- Root-level duplicate `verification-before-completion` was removed; keep only the OpenHarness namespaced version for completion gates.
- Consider adding command-output capture fields to `STATUS.yaml` if completion evidence should become more machine-readable.
