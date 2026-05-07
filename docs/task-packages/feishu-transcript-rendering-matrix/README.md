# OR-022 Feishu Transcript Rendering Matrix

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Summary
- 梳理 openrelay 在飞书流式回复与最终 `Execution Log` 中可能出现的过程输出类型，建立渲染矩阵，并用 `lark-cli` 发送真实飞书卡片样例验证排版效果。

## Current Status
- 当前处于需求收敛阶段。已确认问题来自过程日志渲染面，而不是业务回复重复发送；后续需要先完成输出类型矩阵和真实飞书样例验证，再决定实现改法。

## Read This First
- `STATUS.yaml`
- `01-requirements.md`
- `02-overview-design.md`
- `03-detailed-design.md`
- `04-verification.md`
- `05-evidence.md`
