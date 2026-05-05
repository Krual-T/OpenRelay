# Evidence

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Residual Risks
- 飞书官方 CLI / 官方调试工具无法单独证明真实客户端流式 UI，本轮已记录为能力边界。
- 真实飞书手动触发后的 trace 验证样例尚未采集。
- `lark-cli` 本机未安装；本轮只记录官方资料与候选命令，没有执行真实 CLI 调用。

## Manual Steps
- 后续需要人工在飞书触发至少一条测试消息或卡片动作，并用本地 trace 查询验证链路。
- 推荐优先执行 `F-002-status`、`F-008-normal-turn`、`F-009-streaming-card`、`F-010-stop`。

## Files
- `docs/task-packages/feature-inventory-runtime-verification/README.md`
- `docs/task-packages/feature-inventory-runtime-verification/STATUS.yaml`
- `docs/task-packages/feature-inventory-runtime-verification/01-requirements.md`
- `docs/task-packages/feature-inventory-runtime-verification/02-overview-design.md`
- `docs/task-packages/feature-inventory-runtime-verification/03-detailed-design.md`
- `docs/task-packages/feature-inventory-runtime-verification/04-verification.md`
- `docs/task-packages/feature-inventory-runtime-verification/05-evidence.md`
- `docs/research/feishu-official-runtime-tools.md`
- `docs/feature-inventory.md`
- `docs/runtime-verification-matrix.md`

## Commands
- `openharness new-task feature-inventory-runtime-verification --task-id OR-015 --title "Feature Inventory And Runtime Verification" --summary "Map user-visible features to real runtime verification evidence." --owner codex --status proposed`
- `openharness check-tasks` (`final verification command`)
- `uv run pytest tests/runtime/test_help_renderer.py tests/runtime/test_command_router_resume.py tests/runtime/test_command_router_workspace.py tests/runtime/test_command_router_admin.py tests/runtime/test_panel_service.py tests/runtime/test_turn.py tests/storage/test_message_observability.py tests/feishu/test_streaming_session.py`，结果 35 passed。
- `git diff --check`，结果通过。
- `command -v lark-cli || true`，结果为空，说明本机当前没有安装 `lark-cli`。
- `curl -L https://raw.githubusercontent.com/larksuite/cli/main/skills/lark-im/SKILL.md`
- `curl -L https://raw.githubusercontent.com/larksuite/cli/main/skills/lark-event/SKILL.md`
- `curl -L https://raw.githubusercontent.com/larksuite/cli/main/README.zh.md`

## Artifact Paths
- `docs/research/feishu-official-runtime-tools.md`
- `docs/feature-inventory.md`
- `docs/runtime-verification-matrix.md`

## Follow-ups
- 安装并授权 `lark-cli` 后，用测试 chat 执行一次消息发送 / 事件监听 dry run。
- 由用户在真实飞书客户端触发 `F-002-status` 或 `F-008-normal-turn`，维护者用 `openrelay-trace` 采集证据。
- 如果要自动判断矩阵，后续新增窄范围 `openrelay-verify-message`。
