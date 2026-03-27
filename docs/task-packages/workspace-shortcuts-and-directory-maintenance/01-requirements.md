# Requirements

## Goal
继续降低频繁切目录的成本，把最近使用目录、固定目录和快捷目录维护收敛成更自然的飞书体验。

## Problem Statement
当前工作区浏览已经可用，但主路径里仍混有 `main/develop` 这类 release channel 概念。它会把“切目录”和“切版本工作区”两类语义混在一起，导致帮助文案、状态页和面板持续暴露过时的双工作区模型。

## Required Outcomes
1. 用户侧不再支持 `/main`、`/stable`、`/develop` 这类 release channel 切换命令。
2. `/help`、`/status`、面板头部与会话列表等主路径 UI 不再继续展示 `main/develop` channel 概念。
3. 工作区切换主路径统一收敛到 `/workspace` 与 `/shortcut`。

## Non-Goals
- 本轮不强制删除底层存储中的 `release_channel` 字段，也不做数据库迁移。
- 本轮不重做快捷目录 channel 过滤模型；先移除用户可见的 release 切换主路径。

## Constraints
- 要优先保证主路径语义收敛，避免“命令已移除但 UI 还在暗示 channel”。
- 底层兼容字段可以暂留，但不能继续成为用户操作入口。
