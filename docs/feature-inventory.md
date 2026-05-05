# Feature Inventory

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Scope
本清单服务 OR-015。每个条目都把用户入口、用户可见 UI、实际运行副作用、状态持久化和可观测证据拆开，避免把“有回复”误判为“runtime 正确执行”。

## Inventory
| Feature ID | User Entry | Expected User UI | Runtime Effect | Persistent State | Observable Evidence |
| --- | --- | --- | --- | --- | --- |
| `F-001-help` | 发送 `/help` 或 `/tools` | 返回 OpenRelay 帮助文本，包含当前可用命令，不暴露已移除的 `/main`、`/develop` | `RuntimeCommandRouter` 识别 control command，调用 help renderer | 不改变会话状态 | trace 出现 `ingress.message.received`、`dispatch.command.detected`、`reply.sent`；`tests/runtime/test_help_renderer.py` 覆盖内容 |
| `F-002-status` | 发送 `/status` | 返回当前 runtime 状态、活跃任务或空闲信息 | 调用 `RuntimeStatusPresenter`，允许在活跃 run 期间旁路执行 | 不应切换 session / workspace | trace 出现 command 分支和 `reply.sent`；人工核对文本与当前活跃 run 一致 |
| `F-003-resume-list` | 顶层私聊发送 `/resume` | 返回可恢复后端会话卡片，支持分页按钮 | 调用 session browser / panel service，生成 interactive card | 不切换 native session，只展示列表 | trace 出现 command 分支；飞书出现卡片；`tests/runtime/test_command_router_resume.py` 覆盖列表参数 |
| `F-004-resume-latest` | 顶层私聊发送 `/resume latest` | 返回已连接最新后端会话的文本，提示后续直接发消息 | 解析 latest，绑定当前 relay session 到最新 native session | `SessionRecord.native_session_id` 更新 | trace 的 `session.loaded` / 后续 `storage.session.saved` 可关联；SQLite session 记录包含新 native session |
| `F-005-workspace-browser` | 顶层私聊发送 `/workspace` 或 `/ws` | 返回工作区浏览卡片，可分页 / 搜索 / 进入目录 | 调用 workspace browser，发送 interactive card | 不立即切换 cwd，除非后续选择 | trace 出现 command 分支；飞书出现 workspace 卡片；`tests/runtime/test_command_router_workspace.py` 覆盖基础路径 |
| `F-006-workspace-select` | 发送 `/workspace select <path>` 或卡片选择目录 | 返回工作区已切换提示，说明下一条真实消息使用新 thread | 修改当前 session 工作目录和后续 session scope | `SessionRecord.cwd` 或绑定记录更新 | trace 出现 command 分支和 `reply.sent`；SQLite session cwd 变化；真实下一条消息进入新工作区 |
| `F-007-shortcut` | 发送 `/shortcut add/list/use/remove ...` | 返回快捷目录保存、列表、切换或删除结果 | 调用 shortcut service 管理目录别名 | shortcut store 增删改；`use` 会触发 workspace 切换 | trace 出现 command 分支和 `reply.sent`；SQLite / store 中 shortcut 状态变化 |
| `F-008-normal-turn` | 发送非 `/` 普通消息 | 先出现 typing / 流式卡片，最终显示完整回复 | 进入 backend turn，创建或复用 native session，驱动 agent runtime | session 消息历史追加 user / assistant，usage 与 native session 持久化 | trace 出现 `dispatch.turn.accepted`、`turn.started`、backend runtime events、`storage.session.saved`、`reply.sent` |
| `F-009-streaming-card` | 普通消息触发且 `stream_mode=card` | 飞书里出现 thinking / streaming 卡片，内容随 assistant delta 更新，完成后变最终卡片 | `FeishuStreamingSession` 创建 CardKit 卡片，调用 card settings / element content / card update | streaming message alias 被记住，最终 reply id 写入 trace | 本地日志含 streaming update；trace 最终 `reply.sent` payload `streaming=true`；真实 UI 需人工观察 |
| `F-010-stop` | 活跃回复期间发送 `/stop` | 返回已发送停止请求；流式卡片变为已停止最终卡片 | `RuntimeMessageApplicationService.handle_stop` 取消 active run | 当前 run cancel event 置位；不应保存完整 assistant 回复为成功结果 | trace 出现 `/stop` command、停止回复 `reply.sent`；活跃 run 结束；`tests/runtime/test_turn.py` 覆盖流式卡片关闭 |
| `F-011-card-pagination` | 点击 `/resume` 或 `/workspace` 卡片分页按钮 | 原卡片原地更新到目标页 | `parse_card_action_event` 转成 `IncomingMessage(source_kind=card_action)`，panel service 使用 `update_message_id` | 不改变业务 session，除非 action 是选择类 | trace 出现 card action message；飞书同一消息卡片更新；`tests/runtime/test_panel_service.py` 覆盖原地更新 |
| `F-012-card-form-action` | 在卡片表单输入后提交，例如带目录搜索或选择值 | 原卡片更新或返回对应命令结果 | card action 的 `form_value` 合成命令参数后进入 command router | 视命令而定，可能更新 workspace / shortcut | trace 的 incoming message `source_kind=card_action`；命令分支与结果 reply / card update |
| `F-013-thread-follow-up` | 在活跃回复期间继续发送补充消息 | 如果 backend 支持 live input 则吸收，否则返回排队提示并稍后执行 | active run 锁命中，进入 live input 或 queued follow-up | follow-up 队列短期存在；dequeue 后进入 turn | trace 出现 `queue.follow_up.enqueued` / `queue.follow_up.dequeued`；UI 先出现排队确认 |
| `F-014-removed-command` | 发送 `/panel` 或历史 release 命令 | `/panel` 返回迁移提示；未实现命令提示使用 `/help` | command router 拦截或返回未实现 | 不改变状态 | trace 出现 command 分支和 `reply.sent`；`tests/runtime/test_command_router_admin.py` 覆盖 |

## Coverage Notes
- `pytest` 主要证明解析、路由、卡片 payload 和状态迁移。
- `openrelay-trace` 主要证明真实飞书事件进入 openrelay 后的 runtime 链路。
- 飞书客户端 UI 是否真正看到流式更新，当前只能通过人工观察确认。
- `lark-cli` 可以作为触发与旁路查询工具，但不能单独证明真实客户端 UI。
