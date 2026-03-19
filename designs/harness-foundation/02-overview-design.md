# Overview Design

## Core Model
仓库内 harness 收敛成三层：

1. `AGENTS.md` 作为地图
   - 说明仓库事实来源、默认工作流、验证协议与结构约束。
   - 不承载任务细粒度状态。
2. `designs/<task>/` 作为任务包
   - 每个任务包都是单独的事实单元。
   - 通过固定文件布局表达需求、总体设计、详细设计、验证与证据。
3. `.harness/manifest.yaml` + `scripts/harness/*` 作为执行入口
   - 提供机器可读 discovery order、状态流、目录协议与检查脚本。

## Why Design Packages Instead Of Task Board First
- 一个设计包可以同时承载任务背景、设计分层、验证方案和落地证据，避免任务板和设计稿双写。
- agent 可以按固定顺序读取，不需要先跳任务板再跳设计文档。
- 未来迁移到别的项目时，只需要复制 `AGENTS.md` 结构约定、`.harness/manifest.yaml` 和 skill，而不需要绑定到特定 TaskBoard 风格。

## Design Package Layout
每个 design package 固定包含：
- `README.md`：入口页与导航页。
- `STATUS.yaml`：机器可读状态源。
- `01-requirements.md`：需求与完成定义。
- `02-overview-design.md`：总体设计与边界。
- `03-detailed-design.md`：详细设计与文件级落点。
- `04-verification.md`：验证方案与结果。
- `05-evidence.md`：改动证据与 follow-up。

## Harness Commands
- `scripts/harness/bootstrap.py`
  - 读取 manifest，列出 active design packages。
- `scripts/harness/check_designs.py`
  - 校验 design package 必需文件和 `STATUS.yaml` 关键字段。
- `scripts/harness/verify.py`
  - 先跑 design protocol check，再根据 design package 声明执行验证命令。
