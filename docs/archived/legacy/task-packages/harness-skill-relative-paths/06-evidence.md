# Evidence

## Files
- `AGENTS.md`
- `.project-memory/facts/design_packages_are_task_source.yaml`
- `docs/archived/legacy/task-packages/harness-skill-relative-paths/README.md`
- `docs/archived/legacy/task-packages/harness-skill-relative-paths/STATUS.yaml`
- `docs/archived/legacy/task-packages/harness-skill-relative-paths/01-requirements.md`
- `docs/archived/legacy/task-packages/harness-skill-relative-paths/02-overview-design.md`
- `docs/archived/legacy/task-packages/harness-skill-relative-paths/03-detailed-design.md`
- `docs/archived/legacy/task-packages/harness-skill-relative-paths/04-implementation-plan.md`
- `docs/archived/legacy/task-packages/harness-skill-relative-paths/05-verification.md`
- `docs/archived/legacy/task-packages/harness-skill-relative-paths/06-evidence.md`
- `../openharness/skills/using-openharness/SKILL.md`
- `../openharness/skills/using-openharness/scripts/openharness.py`

## Commands
- `.agents/skills/openharness/using-openharness/scripts/openharness.py new-design harness-skill-relative-paths OR-018 "Harness Skill Relative Paths" --owner codex --summary "Remove hardcoded harness installation paths and environment-specific wrapper commands from the repository protocol."`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py bootstrap --repo .`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks --repo .`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py verify OR-018 --repo .`
- `! rg -n "\.codex/skills/openharness|uv run python .*openharness\.py" AGENTS.md docs .project-memory -S -g '!docs/archived/legacy/task-packages/harness-skill-relative-paths/**' -g '!docs/archived/legacy/task-packages/harness-skill-relative-paths/**'`

## Follow-ups
- If other shared skills still embed `.codex`-specific command forms, migrate them with the same split between skill-local relative paths and repo-root linked paths.
