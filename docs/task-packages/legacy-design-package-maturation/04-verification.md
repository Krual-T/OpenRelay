# Verification

## Required Commands
- `openharness check-tasks`

## Expected Outcomes
- The remaining historical package-maturation work has a dedicated package.
- `OR-010` 到 `OR-013` 的成熟度、主要缺口、推进顺序和 handoff 边界已经写清楚。
- 本包可以进入 `detailed_ready`，但不宣称任何目标产品包已经完成。

## Latest Result
- 2026-03-19: package scaffolded as the explicit follow-up to OR-016.
- 2026-03-26: repository package roots were migrated from `docs/designs` / `docs/archived/designs` to `docs/task-packages` / `docs/archived/task-packages`, and `AGENTS.md` verification guidance was aligned from `check-designs` to `check-tasks`.
- 2026-03-27: `openharness bootstrap` 确认 active root 为 `docs/task-packages`，且当前仓库实际入口是全局 `openharness` 命令，不再是仓库内 `openharness.py` 脚本路径。
- 2026-03-27: `openharness check-tasks` 通过；active package 已完成新版 `04-verification.md` / `05-evidence.md` 迁移。
- 2026-05-05: 已补充历史包成熟化分层和执行顺序；`openharness check-tasks` 通过，输出确认验证了 8 个 task package。
