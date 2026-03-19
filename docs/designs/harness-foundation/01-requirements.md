# Requirements

## Goal
建立一套可跨项目复用的 harness 基础协议，让 agent 在进入仓库后能通过 `AGENTS.md` 定位事实来源，并以 `docs/designs/<task>/` 作为唯一任务包完成设计、实现、验证与证据回写。

## Problem Statement
当前仓库的早期设计任务主要围绕历史遗留任务记录组织，这对单仓库可行，但不利于迁移到其他项目，也不利于让 skill 直接发现“该读什么、该更新什么、如何判断完成”。

## Required Outcomes
1. `AGENTS.md` 明确收敛为 repository map，而不是任务状态数据库。
2. 任务的事实来源从 legacy task notes 切换为 `docs/designs/<task>/` 设计包。
3. 设计包内显式区分需求、总体设计、详细设计、验证、证据。
4. harness 有机器可读入口，能发现设计包、校验协议、输出当前 active package。
5. 仓库内 skill 能指导 agent 以统一顺序读取和更新设计包。

## Non-Goals
- 不在本轮实现完整 scenario replay engine。
- 不在本轮实现 worktree orchestration 或自动 PR 流水线。
- 不在本轮清理全部历史材料；legacy 文档允许暂时保留，但不再作为当前任务事实源。

## Constraints
- 保持 `uv` 作为脚本执行入口。
- 结构必须足够简单，能复用到没有复杂产品后台的普通代码仓库。
- 新协议不能依赖聊天上下文，必须落在仓库文件里。
