# Evidence

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Residual Risks
- 飞书官方 CLI / 官方调试工具无法单独证明真实客户端流式 UI，本轮已记录为能力边界。
- 已采集真实飞书普通消息、独立 CLI 主动命令、只读命令、可交互卡片展示和一条 `/resume` card action 点击样例，但停止型和 card action 后续回复样例尚未采集。
- `/resume`、`/workspace`、`/help` 的 interactive card 能从飞书消息查询看到，但当前 card sender 没有写入 `egress/reply.sent` trace。
- 真实 `/resume` 卡片点击已暴露两个缺口：成功文案把子 thread 继续误写为顶层继续；已有 `relay_session_bindings` 时，新 `native_session_id` 可能被旧绑定覆盖。
- `feishu-cli` profile 已独立于 openrelay 应用配置，并已补授权 `search:message` 与 `im:message.send_as_user`。
- 仓库内 `data/openrelay.sqlite3` 不是当前服务运行库；真实运行库位于 `~/.openrelay/data/openrelay.sqlite3`。

## Manual Steps
- 2026-05-05：用户在真实飞书 OpenRelay P2P 会话发送 `你好`。
- 维护者使用 `lark-cli im +messages-search --as user --query '你好'` 定位到 OpenRelay P2P `chat_id=oc_7bea2cfa55a47c1d33fb0fdc607153f2` 和 incoming message id `om_x100b50a2e81b90b8c353b701aa42e0b`。
- 维护者使用 `uv run openrelay-trace --db ~/.openrelay/data/openrelay.sqlite3 --message-id om_x100b50a2e81b90b8c353b701aa42e0b --json` 验证链路。
- 2026-05-05：维护者使用独立 `feishu-cli` profile 发送 `/status OR-015 cli dry run 2026-05-05 12:08`，消息 id 为 `om_x100b50a2f69548a0c43828d7fad1bb7`。
- 维护者使用 `uv run openrelay-trace --db ~/.openrelay/data/openrelay.sqlite3 --message-id om_x100b50a2f69548a0c43828d7fad1bb7 --json` 验证 `/status` 命令链路。
- 2026-05-05：维护者使用独立 `feishu-cli` profile 发送 `/resume` 和 `/workspace`，飞书消息查询分别显示 `<card title="Relay codex thread histories">...` 和 `<card title="openrelay workspace">...`。
- 2026-05-05：维护者使用独立 `feishu-cli` profile 发送 `/shortcut list`、`/usage`、`/model`、`/sandbox`、`/backend list`、`/panel`，并用 SQLite trace 验证 command 与 reply。
- 2026-05-05：用户点击 `/resume` 卡片里的连接按钮，成功回复为 `om_x100b50a3f2601078c36aa644eccf2de`。维护者用 `message_event_log`、`sessions`、`session_key_aliases`、`relay_session_bindings` 分析确认：目标行为应为回复该成功消息继续已连接会话，顶层普通消息应开启新对话。
- 后续推荐优先执行 `F-010-stop` 和 card action 样例。

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
- `uv run pytest tests/session/test_binding_store.py tests/runtime/test_command_router_resume.py tests/runtime/test_reply_policy.py tests/feishu/test_parsing.py tests/runtime/test_message_observability.py`，结果 30 passed。
- `git diff --check`，结果通过。
- `command -v lark-cli || true`，结果为空，说明本机当前没有安装 `lark-cli`。
- `curl -L https://raw.githubusercontent.com/larksuite/cli/main/skills/lark-im/SKILL.md`
- `curl -L https://raw.githubusercontent.com/larksuite/cli/main/skills/lark-event/SKILL.md`
- `curl -L https://raw.githubusercontent.com/larksuite/cli/main/README.zh.md`
- `lark-cli im +messages-search --as user --query '你好' --page-size 20 --format json`
- `sqlite3 -header -column ~/.openrelay/data/openrelay.sqlite3 "select id, occurred_at, stage, event_type, chat_id, incoming_message_id, reply_message_id, source_kind, summary from message_event_log order by id desc limit 40;"`
- `uv run openrelay-trace --db ~/.openrelay/data/openrelay.sqlite3 --message-id om_x100b50a2e81b90b8c353b701aa42e0b --json`
- `lark-cli im +messages-send --as user --chat-id 'oc_7bea2cfa55a47c1d33fb0fdc607153f2' --text '/status OR-015 cli dry run 2026-05-05 12:08'`
- `uv run openrelay-trace --db ~/.openrelay/data/openrelay.sqlite3 --message-id om_x100b50a2f69548a0c43828d7fad1bb7 --json`
- `lark-cli im +messages-send --as user --chat-id 'oc_7bea2cfa55a47c1d33fb0fdc607153f2' --text '/resume'`
- `lark-cli im +messages-send --as user --chat-id 'oc_7bea2cfa55a47c1d33fb0fdc607153f2' --text '/workspace'`
- `lark-cli im +chat-messages-list --as user --chat-id 'oc_7bea2cfa55a47c1d33fb0fdc607153f2' --page-size 8 --sort desc --format json`
- `lark-cli im +messages-send --as user --chat-id 'oc_7bea2cfa55a47c1d33fb0fdc607153f2' --text '/shortcut list'`
- `lark-cli im +messages-send --as user --chat-id 'oc_7bea2cfa55a47c1d33fb0fdc607153f2' --text '/usage'`
- `lark-cli im +messages-send --as user --chat-id 'oc_7bea2cfa55a47c1d33fb0fdc607153f2' --text '/model'`
- `lark-cli im +messages-send --as user --chat-id 'oc_7bea2cfa55a47c1d33fb0fdc607153f2' --text '/sandbox'`
- `lark-cli im +messages-send --as user --chat-id 'oc_7bea2cfa55a47c1d33fb0fdc607153f2' --text '/backend list'`
- `lark-cli im +messages-send --as user --chat-id 'oc_7bea2cfa55a47c1d33fb0fdc607153f2' --text '/panel'`
- `sqlite3 ~/.openrelay/data/openrelay.sqlite3 "select id,stage,event_type,summary,incoming_message_id,reply_message_id,chat_id,root_id,thread_id,parent_id,source_kind,session_key,relay_session_id,native_session_id,payload_json from message_event_log where id>=821 order by id;"`
- `sqlite3 ~/.openrelay/data/openrelay.sqlite3 "select session_id,base_key,native_session_id,label,cwd,updated_at from sessions where base_key like '%oc_7bea2cfa55a47c1d33fb0fdc607153f2%' order by updated_at desc limit 20;"`
- `sqlite3 ~/.openrelay/data/openrelay.sqlite3 "select alias_key, base_key, updated_at from session_key_aliases where alias_key like '%oc_7bea2cfa55a47c1d33fb0fdc607153f2%' order by updated_at desc limit 80;"`

## Artifact Paths
- `docs/research/feishu-official-runtime-tools.md`
- `docs/feature-inventory.md`
- `docs/runtime-verification-matrix.md`
- `~/.openrelay/data/openrelay.sqlite3`，真实运行 trace 数据库。

## Follow-ups
- 由用户或 CLI 触发 `F-010-stop`，维护者用 `openrelay-trace` 采集证据。
- 服务重启后，继续补一条真实 `/resume` 成功消息的子 thread 回复样例，确认后端继续使用已连接 Codex 会话。
- 继续补一条 workspace 卡片 action 样例，确认 card action trace。
- 补 card sender 的 `egress/reply.sent` 或等价 trace，否则 `/help`、`/resume`、`/workspace` 无法完全由本地 trace 自动判定。
- 如果要自动判断矩阵，后续新增窄范围 `openrelay-verify-message`。
