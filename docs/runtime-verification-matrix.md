# Runtime Verification Matrix

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Evidence Classes
| Class | Meaning |
| --- | --- |
| `pytest` | 本地自动化测试，验证解析、路由、卡片结构或状态迁移 |
| `local_trace` | 用 `openrelay-trace` 查询真实运行后的 SQLite trace |
| `sqlite_state` | 直接核对 session、shortcut、message history 等持久化状态 |
| `real_feishu_manual` | 用户在真实飞书客户端触发并人工观察 UI |
| `official_cli_optional` | 安装授权后用 `lark-cli` 发送消息、监听事件或查询消息 |

## Common Trace Commands
```bash
uv run openrelay-trace --message-id "$MESSAGE_ID" --json
uv run openrelay-trace --trace-id "$TRACE_ID" --json
uv run openrelay-trace --session-id "$RELAY_SESSION_ID" --json --limit 100
uv run openrelay-trace --turn-id "$TURN_ID" --json
```

当前长期运行的 `openrelayd` 使用 `~/.openrelay/data/openrelay.sqlite3`，真实运行验证应显式传入：

```bash
uv run openrelay-trace --db ~/.openrelay/data/openrelay.sqlite3 --message-id "$MESSAGE_ID" --json
```

## Matrix
| Feature ID | Primary Verification | Required Runtime Evidence | UI Evidence | Official Tool Role | Known Blind Spot |
| --- | --- | --- | --- | --- | --- |
| `F-001-help` | `pytest` + `local_trace` | `dispatch.command.detected` summary `/help`；`reply.sent` | 帮助文本包含 `/resume`、`/workspace`、`/status`，不包含已移除入口 | 可用 `lark-cli im +messages-send` 发送 `/help`，用 `+messages-mget` 查回复 | CLI 查到消息不代表用户视觉布局正确 |
| `F-002-status` | `real_feishu_manual` + `local_trace` | command 分支；`reply.sent`；活跃 run 时不进入 queue | 状态文本与当前运行状态一致 | 可监听 `im.message.receive_v1` 确认输入事件 | 当前 trace 不保证 status 文本语义逐字段正确 |
| `F-003-resume-list` | `pytest` + `real_feishu_manual` | command 分支；卡片发送或更新对应 reply id | 飞书出现会话列表卡片和分页按钮 | 可查询 interactive 消息存在 | interactive 卡片内容查询能力有限，仍需人工看按钮 |
| `F-004-resume-latest` | `pytest` + `sqlite_state` + `local_trace` | `session.loaded` 后有 command reply；后续 turn 使用新 native session | 文本提示已连接最新 session | 可用 CLI 发送命令和查询回复 | 最新 session 的选择正确性依赖 backend session browser |
| `F-005-workspace-browser` | `pytest` + `real_feishu_manual` | command 分支；panel card 发送 | 飞书出现 workspace 浏览卡片 | 可查询卡片消息存在 | CLI 不证明目录列表视觉可用 |
| `F-006-workspace-select` | `pytest` + `sqlite_state` + `local_trace` | command 分支；`reply.sent`；后续 `session.loaded.payload.cwd` 变更 | 文本提示工作区切换成功 | 可用 CLI 发送选择命令 | 需要下一条真实消息验证新 thread / cwd 生效 |
| `F-007-shortcut` | `pytest` + `sqlite_state` | command 分支；`reply.sent`；shortcut store 状态符合 add/use/remove | 用户看到保存、列表、切换、删除结果 | 可用 CLI 批量发送命令 | `use` 的真实效果需和下一条 turn 一起验证 |
| `F-008-normal-turn` | `real_feishu_manual` + `local_trace` | `dispatch.turn.accepted`、`turn.started`、backend event、`storage.session.saved`、`reply.sent` | 看到 typing / 流式卡片 / 最终回复 | CLI 可发送测试 prompt、查询最终消息 | CLI 不能证明中间流式变化被客户端展示 |
| `F-009-streaming-card` | `real_feishu_manual` + `local_trace` + 日志 | trace 最终 `reply.sent.payload.streaming=true`；日志有 CardKit update；无 `reply.failed` | 人工确认卡片从 thinking 到 delta 更新再到最终卡片 | CLI 可查询最终 interactive 消息存在 | 目前没有官方工具能单独证明流式 UI 时间线 |
| `F-010-stop` | `pytest` + `real_feishu_manual` + `local_trace` | `/stop` command；停止确认 `reply.sent`；当前 run 结束；无后续 stale streaming update | 看到停止确认，原流式卡片变“已停止当前回复” | CLI 可在测试 chat 发送 `/stop` | cancel 到 backend 终止之间可能有短暂延迟 |
| `F-011-card-pagination` | `pytest` + `real_feishu_manual` | card action incoming；command 分支；同一 `update_message_id` 更新 | 点击分页后原卡片更新，不新增重复卡片 | `lark-event` 可辅助捕获 raw card action event | compact conversion 不支持 interactive 卡片，raw event 仍需人工解读 |
| `F-012-card-form-action` | `real_feishu_manual` + `local_trace` | card action incoming 的 text 包含 form 参数；命令分支执行 | 表单提交后看到对应结果 | `lark-event` 可辅助留存 raw action | 表单输入值映射错误可能只在真实 action 中暴露 |
| `F-013-thread-follow-up` | `real_feishu_manual` + `local_trace` | active lock 命中；`queue.follow_up.enqueued` 或 live input；后续 dequeue | 用户先看到排队确认或当前卡片继续更新 | CLI 可构造连续消息，但时序仍需人工控制 | race condition 需要真实长任务才能稳定复现 |
| `F-014-removed-command` | `pytest` + `local_trace` | command 分支；`reply.sent` 文本是迁移或未实现提示 | 用户不会看到旧命令继续执行 | CLI 可发送历史命令回归 | 只覆盖已知移除入口，不覆盖未知旧文档残留 |

## Real Feishu Dry Run
最小真实验收流程：

1. 用户在测试飞书会话发送唯一消息，例如 `OR-015 dry run /status 2026-05-05T120000`。
2. 如果使用 CLI，维护者先运行：

```bash
lark-cli event consume im.message.receive_v1 --max-events 1 --timeout 30s --as bot
```

3. 从飞书事件或 openrelay 日志拿到 `message_id`，再查询：

```bash
uv run openrelay-trace --message-id "$MESSAGE_ID" --json
```

4. 判断通过条件：
   - 有 `ingress.message.received`。
   - 有 `session.key.resolved` 和 `session.loaded`。
   - `/status` 类命令有 `dispatch.command.detected` 和 `reply.sent`。
   - 普通消息类 turn 有 `dispatch.turn.accepted`、`turn.started`、`storage.session.saved`、`reply.sent`。
   - 真实飞书 UI 与功能清单里的 `Expected User UI` 一致。

## Executed Dry Runs
| Date | Feature | Trigger | Message ID | Result | Evidence |
| --- | --- | --- | --- | --- | --- |
| 2026-05-05 | `F-008-normal-turn` / `F-009-streaming-card` | 用户在真实飞书 OpenRelay P2P 会话发送 `你好` | `om_x100b50a2e81b90b8c353b701aa42e0b` | 通过一条基础链路验证；trace 包含 ingress、session、dispatch、turn、storage、reply | `~/.openrelay/data/openrelay.sqlite3`；reply id `om_x100b50a2e83734a4c3cf7c946800763`；`reply.sent.payload.streaming=true` |
| 2026-05-05 | `F-002-status` | 独立 `feishu-cli` profile 向 OpenRelay P2P 会话发送 `/status OR-015 cli dry run 2026-05-05 12:08` | `om_x100b50a2f69548a0c43828d7fad1bb7` | 通过一条 CLI 主动触发链路验证；trace 包含 ingress、session、command、reply | `~/.openrelay/data/openrelay.sqlite3`；reply id `om_x100b50a2f6a720a0c1477d9a3339a80`；`dispatch.command.detected` summary `/status` |
| 2026-05-05 | `F-001-help` | 独立 `feishu-cli` 发送 `/help OR-015 command dry run 2026-05-05 12:18` | `om_x100b50a2b8f1b8acc42faee09166a94` | 飞书消息查询能看到 help interactive card；trace 记录 command detected，但未记录卡片 `reply.sent` | help card id `om_x100b50a2b887e0a0c2df3105406b4ea`；观测缺口同 card sender |
| 2026-05-05 | `F-003-resume-list` | 独立 `feishu-cli` 发送 `/resume` | `om_x100b50a2b4ca68a4c4c57c40decce7a` | 飞书消息查询能看到 resume interactive card；trace 记录 command detected，但未记录卡片 `reply.sent` | resume card id `om_x100b50a2b4db5ca8c2a87002bc74362`；CLI 显示 `<card title="Relay codex thread histories">...` |
| 2026-05-05 | `F-005-workspace-browser` | 独立 `feishu-cli` 发送 `/workspace` | `om_x100b50a2b03b84b0c3841715ca91198` | 飞书消息查询能看到 workspace interactive card；trace 记录 command detected，但未记录卡片 `reply.sent` | workspace card id `om_x100b50a2b1c0f0a0c2a21b39c78dc31`；CLI 显示 `<card title="openrelay workspace">...` |
| 2026-05-05 | `F-007-shortcut` | 独立 `feishu-cli` 发送 `/shortcut list` | `om_x100b50a2b03834a0c1460bdf1b199a6` | 通过；trace 包含 command 和 `reply.sent`，飞书返回当前没有可用快捷目录 | reply id `om_x100b50a2b1c8a0a8c3fa26a838d8343` |
| 2026-05-05 | `F-014-removed-command` | 独立 `feishu-cli` 发送 `/panel` | `om_x100b50a34c9934a4c146a104eeff5c0` | 通过；trace 包含 command 和 `reply.sent`，飞书返回迁移提示 | reply id `om_x100b50a34cbac0a0c352154a1152c27` |

可观测性缺口：通过 `RuntimeReplyService` 发送的文本 / post 命令回复会记录 `egress/reply.sent`；通过 panel / card sender 发送的 interactive card 已能在飞书消息查询中看到，但当前没有对应的 `reply.sent` trace。后续若要让矩阵自动判定 `/help`、`/resume`、`/workspace`，需要补 card sender 的结构化 trace。

## Tooling Direction
短期不新增完整自动化平台。下一步更合适的是扩展 `openrelay-trace` 或新增窄验证命令，例如：

```bash
uv run openrelay-verify-message --message-id "$MESSAGE_ID" --feature F-008-normal-turn
```

这个命令只做矩阵断言：检查 trace stage、event type、reply id 和必要的 SQLite 状态，不宣称 UI 流式显示通过。
