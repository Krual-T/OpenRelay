# Detailed Design

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Runtime Verification Plan
- Verification Path:
- 尚未进入详细设计；真实验证路径待探索后确定。
- Fallback Path:
- 如果飞书真实事件字段不足以自动验证，需要记录人工操作步骤与 trace 查询边界。
- Planned Evidence:
- 预计需要真实 `/resume` card action、多个成功回复 thread、后续普通回复和数据库绑定状态的对应证据。

只有当详细设计已经具体到可以执行时，才进入 `in_progress`。
如果设计已经完成但实现尚未开始，应保持在 `detailed_ready`。

## Files Added Or Changed
- 当前只新增 task package 文档。

## Interfaces
待探索。

## Stage Gates
- overview 已明确产品语义和系统边界。
- 已确定数据库绑定、飞书事件解析、执行锁和 trace 的具体落点。
- 已列出真实运行验证步骤。

## Decision Closure
尚未进入决策关闭。

## Error Handling
待设计。已知静默风险：用户以为自己在某个恢复会话 thread 中继续，但实际消息进入了另一个后端会话。

## Migration Notes
待设计。

## Detailed Reflection
尚未进行。
