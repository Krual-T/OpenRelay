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
- 2026-05-05 已用独立 `feishu-cli` profile 补测 `/help`、`/resume`、`/workspace`、`/shortcut list`、`/usage`、`/model`、`/sandbox`、`/backend list`、`/panel`。
- 2026-05-05 已分析一次真实 `/resume` 卡片点击：成功回复来自 card action，reply id 为 `om_x100b50a3f2601078c36aa644eccf2de`，原文案把“回复成功消息继续”误写成“顶层对话继续”。
- 2026-05-05 已补代码级回归验证，确认 `/resume` 更新已有 `relay_session_bindings` 时不会被旧绑定覆盖，并确认 card action 的成功回复消息会按显式 `session_key` 建立可回复别名。
- Path Notes:
- 当前能验证 task package 结构与文档矩阵完整性。
- 已完成一条真实飞书普通消息 dry run，可证明 `F-008-normal-turn` 和 `F-009-streaming-card` 的基础链路。
- 已完成一条独立 CLI 主动触发 `/status` dry run，可证明 `F-002-status` 的基础链路；尚未完成 `/stop` 和更多 card action 矩阵条目。
- 已确认 `/resume`、`/workspace`、`/help` 的 interactive card 在飞书消息查询中可见，但 card sender 当前没有写入 `egress/reply.sent` trace，这是本轮发现的可观测性缺口。
- 已确认 `/resume` 的目标交互语义应是：恢复成功后回复成功消息所在子 thread 继续该后端会话；在顶层直接发送普通消息仍会开启新的对话。

只有当实现已经完成到足以采集新证据时，才进入 `verifying`。
如果实现仍然延期到后续轮次，就不要使用 `archived`。

## Required Commands
- `openharness check-tasks`
- `uv run pytest tests/runtime/test_help_renderer.py tests/runtime/test_command_router_resume.py tests/runtime/test_command_router_workspace.py tests/runtime/test_command_router_admin.py tests/runtime/test_panel_service.py tests/runtime/test_turn.py tests/storage/test_message_observability.py tests/feishu/test_streaming_session.py`
- `uv run pytest tests/session/test_binding_store.py tests/runtime/test_command_router_resume.py tests/runtime/test_reply_policy.py tests/feishu/test_parsing.py tests/runtime/test_message_observability.py`

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
- 当前已采集真实普通消息、CLI 主动命令消息和可交互卡片展示证据；缺口是停止用例、card action 点击用例和 card sender trace 还不完整。
- 已采集 card action 点击链路并修正文案与绑定一致性；仍需要服务重启后再用真实飞书回复成功消息，采集一条完整继续会话 trace。

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
- 2026-05-05：独立 `feishu-cli` 补测 `/resume` 与 `/workspace` 后，飞书消息查询能看到 card id `om_x100b50a2b4db5ca8c2a87002bc74362` 和 `om_x100b50a2b1c0f0a0c2a21b39c78dc31`；trace 只记录到 `dispatch.command.detected`，没有 `egress/reply.sent`。
- 2026-05-05：独立 `feishu-cli` 补测 `/shortcut list`、`/usage`、`/model`、`/sandbox`、`/backend list`、`/panel`，均有 `dispatch.command.detected` 与 `egress/reply.sent`。
- 2026-05-05：真实 `/resume` 卡片点击 trace 显示 incoming message id `om_x100b50a2b4db5ca8c2a87002bc74362`、reply id `om_x100b50a3f2601078c36aa644eccf2de`；排查发现旧文案误导用户直接在顶层发消息，并发现 `relay_session_bindings` 旧值会覆盖新绑定的状态一致性问题。
- 2026-05-05：`uv run pytest tests/session/test_binding_store.py tests/runtime/test_command_router_resume.py tests/runtime/test_reply_policy.py tests/feishu/test_parsing.py tests/runtime/test_message_observability.py` 通过，30 passed。
- 2026-05-05：总体仍记录为 `insufficient_verification`，原因是矩阵已覆盖普通消息、`/status`、部分只读命令和卡片展示，但停止、card action 点击和 card sender trace 缺口尚未关闭。
- Latest Artifact:
