# Detailed Design

## Files Added Or Changed
- `AGENTS.md`
  - 重写为 repository map，声明 `designs/` 是设计任务事实源，task board 降级为可选索引。
- `.harness/manifest.yaml`
  - 声明 designs root、必需文件、默认状态流与 artifact 根目录。
- `src/openrelay/harness/designs.py`
  - 提供 manifest 加载、design package 发现、协议校验和摘要输出。
- `scripts/harness/bootstrap.py`
  - 输出 active design packages。
- `scripts/harness/check_designs.py`
  - 校验 design packages 完整性。
- `scripts/harness/verify.py`
  - 串联 protocol check 与 design-declared verification commands。
- `scripts/harness/new_design.py`
  - 基于 `.harness/templates/` 脚手架创建新的 design package。
- `.codex/skills/design-harness/SKILL.md`
  - 说明 agent 如何使用这套 harness。
- `tests/harness/test_design_harness.py`
  - 对 manifest 加载、design discovery、design validation 建立最小回归保护。

## Status Schema
`STATUS.yaml` 必需字段：
- `id`
- `title`
- `status`
- `summary`
- `owner`
- `created_at`
- `updated_at`
- `done_criteria`
- `verification`

可扩展字段：
- `depends_on`
- `scope`
- `entrypoints`
- `evidence`

## Active Status Semantics
以下状态被 harness 视作 active：
- `proposed`
- `requirements_ready`
- `overview_ready`
- `detailed_ready`
- `in_progress`
- `verifying`

`bootstrap.py` 默认只列 active packages；加 `--all` 可查看所有包。

## Verification Flow
`verify.py` 流程：
1. 调用 `check_designs.py` 保证协议完整。
2. 选择指定 design package 或全部 active package。
3. 顺序执行 `STATUS.yaml.verification.required_commands`。
4. 输出声明的 scenarios，作为后续 replay harness 的挂载点。
