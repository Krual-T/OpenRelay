# OR-015 Feature Inventory And Runtime Verification

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Summary
- 建立 openrelay 的功能清单与真实运行验证矩阵，把用户可见 UI、实际运行副作用和可观测证据统一对应起来。
- 本包会把飞书官方 CLI 或官方调试工具作为调研方向，但在证据确认前不预设它一定能观测卡片流式 UI 状态。

## Current Status
- Status: `detailed_ready`
- 已完成飞书官方 CLI / 官方调试工具调研、功能清单初稿和真实运行验证矩阵初稿。
- 当前完成路径已经收敛为三条闭环：补 `F-010-stop` 真实停止证据、补至少一条 card action 后续回复证据、补 card sender 的结构化 trace 或明确把它拆成后续 observability 任务。
- 在上述证据补齐前，本包不进入 `verifying` 或 `archived`。

## Read This First
- `STATUS.yaml`
- `01-requirements.md`
- `02-overview-design.md`
- `03-detailed-design.md`
- `04-verification.md`
- `05-evidence.md`
- `docs/research/feishu-official-runtime-tools.md`
- `docs/feature-inventory.md`
- `docs/runtime-verification-matrix.md`
