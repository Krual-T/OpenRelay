# Verification

## Required Commands
- `openharness check-tasks`

## Expected Outcomes
- The remaining historical package-maturation work has a dedicated package.

## Latest Result
- 2026-03-19: package scaffolded as the explicit follow-up to OR-016.
- 2026-03-26: repository package roots were migrated from `docs/designs` / `docs/archived/designs` to `docs/task-packages` / `docs/archived/task-packages`, and `AGENTS.md` verification guidance was aligned from `check-designs` to `check-tasks`.
- 2026-03-27: `openharness bootstrap` 确认 active root 为 `docs/task-packages`，且当前仓库实际入口是全局 `openharness` 命令，不再是仓库内 `openharness.py` 脚本路径。
- 2026-03-27: `openharness check-tasks` 通过；active package 已完成新版 `04-verification.md` / `05-evidence.md` 迁移。
