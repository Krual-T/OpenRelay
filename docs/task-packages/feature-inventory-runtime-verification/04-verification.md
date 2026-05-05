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
  - 2026-05-05 已用真实飞书客户端向 OpenRelay P2P 会话发送 `你好`，并在 `~/.openrelay/data/openrelay.sqlite3` 采集到完整 trace。
  - 2026-05-05 已用独立 `feishu-cli` profile 向 OpenRelay P2P 会话发送 `/status OR-015 cli dry run 2026-05-05 12:08`，并在真实运行库采集到命令链路 trace。
- Path Notes:
- 当前能验证 task package 结构与文档矩阵完整性。
- 已完成一条真实飞书普通消息 dry run，可证明 `F-008-normal-turn` 和 `F-009-streaming-card` 的基础链路。
- 已完成一条独立 CLI 主动触发 `/status` dry run，可证明 `F-002-status` 的基础链路；尚未完成 `/stop` 和更多 card action 矩阵条目。

只有当实现已经完成到足以采集新证据时，才进入 `verifying`。
如果实现仍然延期到后续轮次，就不要使用 `archived`。

## Required Commands
- `openharness check-tasks`
- `uv run pytest tests/runtime/test_help_renderer.py tests/runtime/test_command_router_resume.py tests/runtime/test_command_router_workspace.py tests/runtime/test_command_router_admin.py tests/runtime/test_panel_service.py tests/runtime/test_turn.py tests/storage/test_message_observability.py tests/feishu/test_streaming_session.py`

## Expected Outcomes
- `openharness check-tasks` 应确认新增 task package 结构合法。
- 目标 `pytest` 应确认矩阵引用的高频路由、卡片更新、停止和 trace 基础能力没有被文档调研过程破坏。
- 后续真实运行验证应能从一条飞书测试消息追踪到 openrelay 的 ingress、命令或 turn、reply 证据。
- 真实飞书 `你好` dry run 应能从 incoming message id `om_x100b50a2e81b90b8c353b701aa42e0b` 查到完整链路。

## Traceability
- `01-requirements.md` 定义必须交付功能清单、验证矩阵、官方飞书工具调研和手动触发验证工作流。
- `02-overview-design.md` 定义三层结构和主验证流。
- `docs/research/feishu-official-runtime-tools.md` 回答官方 CLI / 官方调试工具能做什么、不能证明什么。
- `docs/feature-inventory.md` 覆盖 14 个高频功能，超过 10 个功能的成功指标。
- `docs/runtime-verification-matrix.md` 给出真实飞书 dry run 和 trace 判断流程。
- 当前已采集真实普通消息和 CLI 主动命令消息证据；缺口是停止用例和 card action 用例尚未采集。

## Risk Acceptance
- 接受当前只完成 task package 建档，不宣称官方 CLI 能力或真实验证闭环已经成立。
- 接受 `lark-cli` 只能作为真实运行辅助，不作为流式 UI 通过证据。
- 后续如果官方工具不能覆盖 UI 观测，应继续使用人工 UI 观察加本地 trace 判断。

## Latest Result
- 2026-05-04：`openharness check-tasks` 通过，输出确认验证了 7 个 task package。
- 2026-05-05：`openharness check-tasks` 通过，输出确认验证了 7 个 task package。
- 2026-05-05：`uv run pytest tests/runtime/test_help_renderer.py tests/runtime/test_command_router_resume.py tests/runtime/test_command_router_workspace.py tests/runtime/test_command_router_admin.py tests/runtime/test_panel_service.py tests/runtime/test_turn.py tests/storage/test_message_observability.py tests/feishu/test_streaming_session.py` 通过，35 passed。
- 2026-05-05：真实飞书客户端发送 `你好` 后，`uv run openrelay-trace --db ~/.openrelay/data/openrelay.sqlite3 --message-id om_x100b50a2e81b90b8c353b701aa42e0b --json` 查到 `ingress.message.received`、`session.key.resolved`、`session.loaded`、`dispatch.turn.accepted`、`turn.started`、`storage.session.saved`、`turn.completed`、`reply.sent`，reply id 为 `om_x100b50a2e83734a4c3cf7c946800763`。
- 2026-05-05：独立 `feishu-cli` 发送 `/status OR-015 cli dry run 2026-05-05 12:08` 后，`uv run openrelay-trace --db ~/.openrelay/data/openrelay.sqlite3 --message-id om_x100b50a2f69548a0c43828d7fad1bb7 --json` 查到 `ingress.message.received`、`session.key.resolved`、`session.loaded`、`dispatch.command.detected`、`reply.sent`，reply id 为 `om_x100b50a2f6a720a0c1477d9a3339a80`。
- 2026-05-05：总体仍记录为 `insufficient_verification`，原因是矩阵已覆盖普通消息和 `/status`，但停止、resume/workspace 卡片 action 和更多流式边界尚未覆盖。
- Latest Artifact:
