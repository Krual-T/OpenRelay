# Detailed Design

## Files Added Or Changed
- `AGENTS.md`
  - 重写为 repository map，声明 `docs/designs/` 是设计任务事实源，legacy 文档降级为历史证据。
- `.codex/skills/openharness/references/manifest.yaml`
  - 声明 designs root、必需文件、默认状态流与 artifact 根目录。
- `.codex/skills/openharness/scripts/openharness.py`
  - 作为单一 harness CLI，承载 manifest 加载、design package 发现、协议校验、脚手架生成与 verify 子命令。
  - 子命令包括 `bootstrap`、`check-designs`、`new-design`、`verify`。
- `.codex/skills/openharness/SKILL.md`
  - 说明 agent 如何使用这套 harness。
- `.codex/skills/openharness/tests/test_openharness.py`
  - 对 manifest 加载、design discovery、design validation 建立最小回归保护。
  - 同时保证 harness 的实现、入口脚本、测试与 references 全部由 `openharness` skill 自持。

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

`openharness.py bootstrap` 默认只列 active packages；加 `--all` 可查看所有包。

## Verification Flow
`openharness.py verify` 流程：
1. 先执行与 `check-designs` 相同的协议校验。
2. 选择指定 design package 或全部 active package。
3. 顺序执行 `STATUS.yaml.verification.required_commands`。
4. 输出声明的 scenarios，作为后续 replay harness 的挂载点。
