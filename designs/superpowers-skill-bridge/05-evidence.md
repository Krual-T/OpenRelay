# Evidence

## Files
- `.codex/skills/brainstorming`
- `.codex/skills/dispatching-parallel-agents`
- `.codex/skills/executing-plans`
- `.codex/skills/finishing-a-development-branch`
- `.codex/skills/receiving-code-review`
- `.codex/skills/requesting-code-review`
- `.codex/skills/subagent-driven-development`
- `.codex/skills/systematic-debugging`
- `.codex/skills/test-driven-development`
- `.codex/skills/using-git-worktrees`
- `.codex/skills/using-superpowers`
- `.codex/skills/verification-before-completion`
- `.codex/skills/writing-plans`
- `.codex/skills/writing-skills`
- `designs/superpowers-skill-bridge/*`
- `tests/harness/test_design_harness.py`

## Commands
- `uv run python scripts/harness/check_designs.py`
- `find .codex/skills -maxdepth 1 -mindepth 1 -type l | sort`
- `uv run pytest tests/harness/test_design_harness.py`

## Follow-ups
- 如果后续更换 superpowers 安装路径，可加一个 `refresh-superpowers-symlinks` 脚本自动重建。
- 如果后续需要更细的项目级 workflow 约束，可在 design package 里声明推荐 superpowers skills。
