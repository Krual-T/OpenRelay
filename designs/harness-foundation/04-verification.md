# Verification

## Required Commands
- `uv run python scripts/harness/check_designs.py`
- `uv run python scripts/harness/bootstrap.py --all`
- `uv run python scripts/harness/verify.py OR-015`
- `uv run pytest tests/harness/test_design_harness.py`

## Expected Outcomes
- design packages 可被 manifest 正常发现。
- `STATUS.yaml` 关键字段缺失时会被校验脚本报错。
- bootstrap 脚本能输出当前 active design package 摘要。

## Latest Result
- 2026-03-19: `check_designs.py`、`bootstrap.py --all`、`verify.py OR-015`、`pytest tests/harness/test_design_harness.py` 均通过；design package discovery、validation 与脚手架生成回归已覆盖。
