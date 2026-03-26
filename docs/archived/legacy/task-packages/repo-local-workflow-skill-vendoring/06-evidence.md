# Evidence

## Files
- `.agents/skills/brainstorming/SKILL.md`
- `.agents/skills/researching-solutions/SKILL.md`
- `.agents/skills/openharness/using-openharness/references/skill-hub.md`
- `.agents/skills/openharness/using-openharness/tests/test_openharness.py`
- `docs/archived/legacy/task-packages/repo-local-workflow-skill-vendoring/04-implementation-plan.md`
- `docs/archived/legacy/task-packages/repo-local-workflow-skill-vendoring/05-verification.md`
- `docs/archived/legacy/task-packages/repo-local-workflow-skill-vendoring/06-evidence.md`
- `docs/archived/legacy/task-packages/repo-local-workflow-skill-vendoring/STATUS.yaml`
- `docs/archived/legacy/task-packages/openharness-skill-system-refactor/STATUS.yaml`

## Commands
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks --repo .`
- `uv run --extra dev pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py -q`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py verify OR-020 --repo .`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-completion OR-020 --repo .`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py bootstrap --repo .`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py bootstrap --all --repo .`

## Follow-ups
- Vendor additional generic helper skills only if the repository needs fully self-contained execution beyond the current workflow layer.
