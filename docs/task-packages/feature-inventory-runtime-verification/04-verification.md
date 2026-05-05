# Verification

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Verification Path
- Planned Path:
  - 执行 `openharness check-tasks`，确认 task package 结构符合仓库协议。
  - 用文档审查确认功能清单至少覆盖 10 个高频功能，且每项都有 UI、runtime、副作用和证据字段。
  - 用文档审查确认官方飞书工具调研结论没有把 unknown 写成事实。
  - 后续真实验收阶段需要补充至少一条真实飞书 trace 验证证据。
- Executed Path:
  - 2026-05-04 已执行 `openharness check-tasks`。
  - 2026-05-05 已完成官方工具调研、功能清单和验证矩阵写回。
  - 2026-05-05 已执行 `openharness check-tasks`，通过。
  - 2026-05-05 已执行目标 `pytest`，35 个用例通过。
- Path Notes:
  - 当前能验证 task package 结构与文档矩阵完整性。
  - 真实飞书客户端观察和 trace dry run 尚未执行，因此不能宣称真实运行验证闭环完成。

只有当实现已经完成到足以采集新证据时，才进入 `verifying`。
如果实现仍然延期到后续轮次，就不要使用 `archived`。

## Required Commands
- `openharness check-tasks`
- `uv run pytest tests/runtime/test_help_renderer.py tests/runtime/test_command_router_resume.py tests/runtime/test_command_router_workspace.py tests/runtime/test_command_router_admin.py tests/runtime/test_panel_service.py tests/runtime/test_turn.py tests/storage/test_message_observability.py tests/feishu/test_streaming_session.py`

## Expected Outcomes
- `openharness check-tasks` 应确认新增 task package 结构合法。
- 目标 `pytest` 应确认矩阵引用的高频路由、卡片更新、停止和 trace 基础能力没有被文档调研过程破坏。
- 后续真实运行验证应能从一条飞书测试消息追踪到 openrelay 的 ingress、命令或 turn、reply 证据。

## Traceability
- `01-requirements.md` 定义必须交付功能清单、验证矩阵、官方飞书工具调研和手动触发验证工作流。
- `02-overview-design.md` 定义三层结构和主验证流。
- `docs/research/feishu-official-runtime-tools.md` 回答官方 CLI / 官方调试工具能做什么、不能证明什么。
- `docs/feature-inventory.md` 覆盖 14 个高频功能，超过 10 个功能的成功指标。
- `docs/runtime-verification-matrix.md` 给出真实飞书 dry run 和 trace 判断流程。
- 当前缺口是真实运行证据尚未采集。

## Risk Acceptance
- 接受当前只完成 task package 建档，不宣称官方 CLI 能力或真实验证闭环已经成立。
- 接受 `lark-cli` 只能作为真实运行辅助，不作为流式 UI 通过证据。
- 后续如果官方工具不能覆盖 UI 观测，应继续使用人工 UI 观察加本地 trace 判断。

## Latest Result
- 2026-05-04：`openharness check-tasks` 通过，输出确认验证了 7 个 task package。
- 2026-05-05：`openharness check-tasks` 通过，输出确认验证了 7 个 task package。
- 2026-05-05：`uv run pytest tests/runtime/test_help_renderer.py tests/runtime/test_command_router_resume.py tests/runtime/test_command_router_workspace.py tests/runtime/test_command_router_admin.py tests/runtime/test_panel_service.py tests/runtime/test_turn.py tests/storage/test_message_observability.py tests/feishu/test_streaming_session.py` 通过，35 passed。
- 2026-05-05：总体仍记录为 `insufficient_verification`，原因是真实飞书客户端 dry run 和 trace 样例尚未采集。
- Latest Artifact:
