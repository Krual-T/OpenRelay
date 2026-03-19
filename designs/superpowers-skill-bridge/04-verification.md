# Verification

## Required Commands
- `uv run python scripts/harness/check_designs.py`
- `find .codex/skills -maxdepth 1 -mindepth 1 -type l | sort`
- `uv run pytest tests/harness/test_design_harness.py`

## Expected Outcomes
- design packages 仍然协议完整。
- `.codex/skills/` 下能直接看到所有 soft-linked superpowers skills。
- 测试能证明关键 symlink 存在且指向 superpowers 安装根目录。

## Latest Result
- 2026-03-19: 上述命令通过；仓库内已显式 soft-link 全部已安装 superpowers skills。
