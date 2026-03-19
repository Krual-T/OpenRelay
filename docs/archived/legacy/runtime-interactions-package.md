# Runtime Interactions Package

更新时间：2026-03-14

## 背景

`src/openrelay/runtime_interactions.py` 原先同时承担：

- 交互状态模型
- 用户输入与按钮命令解析
- 交互卡片构造
- 各类 approval / elicitation 协议映射

这些逻辑都围绕“运行时交互”，但抽象层级并不一致。继续累积在一个文件里，会让协议细节、展示细节和状态控制继续耦合。

## 本轮调整

- `openrelay.runtime_interactions.models` 保留交互状态与命令常量
- `openrelay.runtime_interactions.formatting` 保留文本规范化与详情拼装
- `openrelay.runtime_interactions.controller` 只保留控制器与流程推进
- `openrelay.runtime_interactions` 包继续作为稳定导出入口

## 结果

- 交互流程仍由 `RunInteractionController` 统一协调
- 卡片构造和文本格式化不再散落在状态模型旁边
- 后续如果继续拆 approval / elicitation 类型，只需要在包内收敛，不必回到单文件继续膨胀
