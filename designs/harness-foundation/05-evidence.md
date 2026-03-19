# Evidence

## Files
- `AGENTS.md`
- `.harness/manifest.yaml`
- `.harness/templates/design-package.README.md`
- `.harness/templates/design-package.STATUS.yaml`
- `.harness/templates/design-package.01-requirements.md`
- `.harness/templates/design-package.02-overview-design.md`
- `.harness/templates/design-package.03-detailed-design.md`
- `.harness/templates/design-package.04-verification.md`
- `.harness/templates/design-package.05-evidence.md`
- `.codex/skills/design-harness/SKILL.md`
- `designs/harness-foundation/*`
- `src/openrelay/harness/__init__.py`
- `src/openrelay/harness/designs.py`
- `src/openrelay/harness/scaffold.py`
- `scripts/harness/bootstrap.py`
- `scripts/harness/check_designs.py`
- `scripts/harness/verify.py`
- `scripts/harness/new_design.py`
- `tests/harness/test_design_harness.py`

## Commands
- `uv run python scripts/harness/check_designs.py`
- `uv run python scripts/harness/bootstrap.py --all`
- `uv run python scripts/harness/verify.py OR-015`
- `uv run pytest tests/harness/test_design_harness.py`

## Follow-ups
- 为 design package 增加 scenario replay artifact 协议。
- 为 harness 增加 task env / worktree orchestration。
- 评估是否将 `docs/TaskBoard.md` 退化为自动生成的索引页。
