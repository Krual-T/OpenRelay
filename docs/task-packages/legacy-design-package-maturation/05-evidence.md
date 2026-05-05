# Evidence

## Files
- `AGENTS.md`
- `docs/task-packages/legacy-design-package-maturation/README.md`
- `docs/task-packages/legacy-design-package-maturation/STATUS.yaml`
- `docs/task-packages/legacy-design-package-maturation/01-requirements.md`
- `docs/task-packages/legacy-design-package-maturation/02-overview-design.md`
- `docs/task-packages/legacy-design-package-maturation/03-detailed-design.md`
- `docs/task-packages/legacy-design-package-maturation/04-verification.md`
- `docs/task-packages/legacy-design-package-maturation/05-evidence.md`
- `docs/task-packages/*`
- `docs/archived/task-packages/*`

## Commands
- `openharness bootstrap`
- `openharness check-tasks` (`final verification command`)
- 2026-05-05: `openharness check-tasks` 通过，输出确认验证了 8 个 task package。
- 2026-05-05: `git diff --check` 通过。

## Follow-ups
- 先进入 `OR-013`：修正 `README.md` 与 `STATUS.yaml` 的状态不一致，并复核是否可进入 `verifying`。
- 再进入 `OR-011`：补当前会话状态模型和集中控制入口设计。
- 然后进入 `OR-010`：基于 OR-011 的状态模型统一等待态交互。
- 最后进入 `OR-012`：在状态和等待态语义稳定后补异步回看体验。
- OR-017 归档前，至少要完成一次目标包 handoff，并把新证据写入目标包自己的 `04-verification.md` / `05-evidence.md`。
