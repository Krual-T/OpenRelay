# Evidence

## Files
- `AGENTS.md`
- `.codex/skills/openharness/references/manifest.yaml`
- `.codex/skills/openharness/references/templates/design-package.README.md`
- `.codex/skills/openharness/references/templates/design-package.STATUS.yaml`
- `.codex/skills/openharness/references/templates/design-package.01-requirements.md`
- `.codex/skills/openharness/references/templates/design-package.02-overview-design.md`
- `.codex/skills/openharness/references/templates/design-package.03-detailed-design.md`
- `.codex/skills/openharness/references/templates/design-package.04-implementation-plan.md`
- `.codex/skills/openharness/references/templates/design-package.05-verification.md`
- `.codex/skills/openharness/references/templates/design-package.06-evidence.md`
- `.codex/skills/openharness/SKILL.md`
- `.codex/skills/openharness/scripts/openharness.py`
- `docs/archived/designs/harness-foundation/*`
- `.codex/skills/openharness/tests/test_openharness.py`

## Commands
- `uv run python .codex/skills/openharness/scripts/openharness.py check-designs`
- `uv run python .codex/skills/openharness/scripts/openharness.py bootstrap --all`
- `uv run python .codex/skills/openharness/scripts/openharness.py verify OR-015`
- `uv run pytest .codex/skills/openharness/tests/test_openharness.py`

## Follow-ups
- 为 design package 增加 scenario replay artifact 协议。
- 为 harness 增加 task env / worktree orchestration。
- 继续强化 package 校验和 drift 防护。
