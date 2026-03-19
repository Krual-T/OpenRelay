# Requirements

## Goal
把 terminal interaction、user input、MCP elicitation 等等待态统一成同一种飞书交互模型。

## Problem Statement
现在不同等待态仍按底层事件类型分散处理；用户能看到卡住，但还不能始终自然地接住输入、选择和确认。

## Required Outcomes
1. 完成正式设计稿，明确等待态分类、统一卡片语义、输入/选择/确认控件边界和不做项。
2. 主路径代码能把至少 terminal interaction、user input、MCP elicitation 三类事件收敛到统一回复入口。
3. 用户提交后能收到稳定的“已发送/继续处理中”反馈，并且线程内能识别当前等待态是否已结束。

## Non-Goals
- 不在 package migration 这一步直接实现功能代码。
- 不在需求未澄清前提前透支更复杂的交互或产品面。

## Constraints
- 当前 package 是从历史遗留任务描述提炼出的正式设计入口。
- 后续实现前仍应补充更细的总体设计和详细设计。
