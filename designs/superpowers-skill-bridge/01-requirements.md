# Requirements

## Goal
让 `openrelay` 仓库把已经安装在本机的 `obra/superpowers` skills 显式暴露为仓库内 `.codex/skills/` 的软链接，从而让 harness、AGENTS map 和后续协作者都能直接看到并使用这些 workflow skills。

## Problem Statement
仅仅知道“本机装了 superpowers”还不够，因为这仍然是隐式依赖：
- 协作者不知道仓库具体依赖哪些 skills。
- 仓库内没有直接可见的 skill 入口。
- design package 和外部 workflow skill 的关系不够直观。

## Required Outcomes
1. `.codex/skills/` 下存在所有已安装 superpowers skills 的软链接。
2. `AGENTS.md` 说明这些 symlink 的来源和用途。
3. 至少有测试验证关键 symlink 存在且指向 superpowers 安装目录。

## Non-Goals
- 不复制 superpowers skill 内容到仓库。
- 不修改 superpowers 上游实现。
- 不改变 `designs/<task>/` 作为任务事实源的地位。

## Constraints
- 使用软链接而不是复制。
- 对当前机器显式可用。
- 仓库私有 skills 仍需与外部 soft-linked skills 并存。
