# Verification

## Required Commands
- `.agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py bootstrap --all`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py verify OR-015`
- `pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py`

## Expected Outcomes
- design packages 可被 manifest 正常发现。
- `STATUS.yaml` 关键字段缺失时会被校验脚本报错。
- bootstrap 脚本能输出当前 active design package 摘要。

## Latest Result
- 2026-03-19: `check-tasks`、`bootstrap --all`、`verify OR-015`、`pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py` 均通过；design package discovery、validation 与脚手架生成回归已覆盖。
- 2026-03-19: harness 入口已收敛为 `.agents/skills/openharness/using-openharness/scripts/openharness.py` 单一 CLI；不再保留 `openrelay.harness` 命名空间，也不再拆分多个 wrapper 脚本。
- 2026-03-19: `.agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks`、`.agents/skills/openharness/using-openharness/scripts/openharness.py bootstrap --all` 与 `pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py` 在单 CLI 重构后再次通过。
