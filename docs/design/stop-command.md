# `/stop` 中断语义

更新时间：2026-03-10

## 背景

`/stop` 之前只是在 runtime 层设置一个取消标记。
当 Codex backend 还卡在 `thread/start`、`thread/resume` 或 `turn/start` 这类请求时，请求本身并不会立刻响应取消，导致用户虽然已经发了 `/stop`，但当前回复仍可能继续跑一段时间，甚至直到请求超时。

## 目标

让 `/stop` 成为一个可靠、可预期的立即中断动作：

- 用户发出 `/stop` 后，系统先立即确认“已收到停止请求”
- 如果当前 turn 已经拿到 `turn_id`，直接向 Codex app-server 发送 `turn/interrupt`
- 如果当前还卡在请求阶段、尚未拿到 `turn_id`，直接取消这次请求，并重置当前会话对应的 app-server client
- 停止完成后，流式卡片、typing、active run 状态都正常回收

## 当前实现

### 1. runtime 侧反馈

`/stop` 现在先回复：`已发送停止请求，正在中断当前回复。`

这条消息表示“请求已经送达”，而不是误导用户认为底层任务已经完全结束。

### 2. Codex backend 的两段式中断

- **请求前阶段**：`thread/start`、`thread/resume`、`turn/start` 都接入了 `cancel_event`
- **turn 运行阶段**：一旦拿到 `turn_id`，继续沿用 `turn/interrupt` 中断当前 turn

### 3. 请求阶段的兜底策略

如果 `/stop` 发生在 `turn_id` 尚未可用的阶段，backend 会：

- 取消当前请求等待
- 清理 pending request
- 重置当前会话绑定的 Codex app-server client
- 以 `interrupted by /stop` 返回上层

这样可以避免“停止请求已经发出，但底层请求还挂着不退”的不确定状态。

### 4. client 隔离

Codex app-server client 现在按本地 `session_id` 隔离，而不是按 workspace/model/sandbox 共享。

这样做的目的不是扩展多实例能力，而是避免一个会话上的强制 reset 误伤另一个会话的正在执行任务。

## 非目标

这次改动不处理以下问题：

- 多条连续消息的排队、合并和覆盖策略
- 多终端 / 多机器人 / 多用户的会话归属模型
- `/stop` 之后是否保留更细粒度的中间输出面板

这些仍属于 `docs/design/open-questions.md` 里其他问题的范围。
