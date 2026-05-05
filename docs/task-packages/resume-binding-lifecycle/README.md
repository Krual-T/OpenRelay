# OR-018 Resume Binding Lifecycle

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Summary
- 明确 `/resume` 后端会话与飞书对话入口之间的生命周期语义，避免多次恢复、多个子 thread、长期保留入口和并发使用时出现会话错乱。
- 本包当前只记录意图，不预设具体实现方案。

## Current Status
- `detailed_ready`：已收敛 `/resume` 生命周期语义、系统边界、实现落点、测试策略和真实飞书验证路径。下一步是按 `03-detailed-design.md` 进入实现或补真实运行证据。

## Read This First
- `STATUS.yaml`
- `01-requirements.md`
- `02-overview-design.md`
- `03-detailed-design.md`
- `04-verification.md`
- `05-evidence.md`
