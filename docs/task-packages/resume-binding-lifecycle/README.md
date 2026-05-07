# OR-018 Resume Binding Lifecycle

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Summary
- 明确 `/resume` 后端会话与飞书对话入口之间的生命周期语义，避免多次恢复、多个子 thread、长期保留入口和并发使用时出现会话错乱。
- 本包已进入实施阶段；当前已修复 `/resume` 卡片点击后因 Codex app-server 大响应读取失败而无可见回复的问题。

## Current Status
- `in_progress`：已收敛 `/resume` 生命周期语义、系统边界、实现落点、测试策略和真实飞书验证路径；2026-05-07 已完成 Codex app-server stdout 大响应读取修复和目标验证。下一步仍需补真实飞书连续入口验证与 native-session 并发边界证据，才能归档。

## Read This First
- `STATUS.yaml`
- `01-requirements.md`
- `02-overview-design.md`
- `03-detailed-design.md`
- `04-verification.md`
- `05-evidence.md`
