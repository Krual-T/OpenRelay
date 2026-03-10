# Panel Single-Card Navigation

## 目标

让飞书里的 `/panel`、`/resume list`、`/help` 这类“导航型卡片”在用户点击按钮时，优先停留在同一张卡片里完成翻页、进入子菜单和返回上一级，而不是每点一次就刷出一条新消息。

这里要解决的不是“所有动作都必须原地更新”，而是把**浏览与导航**和**真正执行状态变化**区分开：

- 浏览与导航尽量留在原卡，保持连续、低噪音。
- 真正改变会话、目录、运行状态的动作，继续复用已有命令主路径，并允许落回文本回复或新消息。

## 信息架构

### 1. 卡片类型分层

这轮把常驻交互卡片分成两类：

- **导航型卡片**：`/panel`、`/resume list`、`/help`
- **执行型动作**：`/resume <id>`、`/cwd`、`/new`、`/clear`、`/main`、`/develop`、`/status`、`/usage`、`/stop` 等

导航型卡片负责“看”和“切换视图”；执行型动作负责真正改变 runtime 状态或输出现场信息。

### 2. `/panel` 的层级模型

`/panel` 继续保持一个总览页和四个结果面：

- `home`
- `sessions`
- `directories`
- `commands`
- `status`

用户的主路径应当是：

1. 打开 `/panel`
2. 进入某个结果面
3. 在同卡内翻页、切排序或返回总览
4. 只有在真正执行动作时，才进入 `/resume`、`/cwd`、`/status` 等已有主链路

这意味着 `/panel` 负责导航，不负责发明第二套执行语义。

## 状态模型

### 1. 不引入服务端卡片状态存储

这轮不新增一层“卡片状态仓库”。

单卡导航所需状态直接由两部分组成：

- **按钮 command**：携带当前视图、页码、排序等渲染所需状态，例如 `/panel sessions --page 2 --sort active-first`
- **动作上下文**：继续沿用现有 `rootId / threadId / sessionKey / sessionOwnerOpenId`

也就是说：

- 视图状态仍然编码在命令里
- 会话归属仍然编码在 action value 里
- “更新哪张卡” 则来自飞书卡片 action webhook 里的 `open_message_id`

这样做的原因很直接：当前系统已经有稳定的 command/value 方案，没有必要再并行维护一份新的卡片状态副本。

### 2. 更新目标

当消息来自卡片动作时：

- webhook 解析出 `reply_to_message_id = open_message_id`
- runtime 把这条 `open_message_id` 视为当前导航卡的更新目标
- 如果这次输出仍是导航型卡片，就优先用消息更新接口覆盖原卡
- 如果更新失败，再退回现有“回复一条新卡 / 文本”的兜底路径

## 返回路径

### `/panel`

- `home -> sessions -> home`
- `home -> directories -> home`
- `home -> commands -> home`
- `home -> status -> home`
- `help -> panel`
- `resume list -> panel`

返回路径不额外引入“面包屑状态机”，而是直接复用已有按钮命令：

- 返回总览：`/panel`
- 进入会话结果：`/panel sessions`
- 打开帮助：`/help`

这样按钮语义与手动命令保持一致，不会出现“按钮能做、手打不能做”的双轨行为。

## 哪些动作原地更新，哪些不原地更新

### 优先原地更新

- `/panel`
- `/panel sessions --page/--sort`
- `/panel directories`
- `/panel commands`
- `/panel status`
- `/resume list --page/--sort`
- `/help`

它们的共同特点是：都只是把用户带到另一个浏览视图，本身不改变真实会话状态。

### 继续走现有主路径

- `/resume latest`
- `/resume <session_id|token>`
- `/cwd`、`/cd`
- `/new`
- `/clear`
- `/main`、`/develop`
- `/status`、`/usage`
- `/stop`

这些动作要么改变当前会话指针、目录或运行状态，要么输出明确的状态文本，因此不强行覆盖当前导航卡，而是继续保留现有回复语义。

## 与现有 command/value 方案的兼容

这轮刻意不新增新的 action schema。

按钮仍然只写两类信息：

- `command`
- 现有 action context（`rootId / threadId / sessionKey / sessionOwnerOpenId`）

因此兼容性策略很简单：

- 老按钮仍然能工作
- 新的“单卡导航”只是在发送层多了一步“若是导航卡，则优先更新原消息”
- runtime 的命令解析与 session 归属逻辑不需要分叉

## 最小落地范围

这轮关闭条件对应的最小实现范围是：

1. `/panel sessions` 在卡片按钮翻页 / 切排序时优先原地更新
2. `/panel` 主卡进入子结果面并返回总览时优先原地更新
3. `/resume list` 分页时优先原地更新
4. `/help` 点击 `/panel` 时优先切到同一张面板卡
5. README 与帮助文案明确新的“同卡导航”心智

## 验收方式

自动化测试覆盖：

- `/panel` 从总览进入 `sessions` 再返回 `home` 时，runtime 会把原卡 message_id 作为更新目标
- `/resume list` 点击下一页时，runtime 会把原卡 message_id 作为更新目标
- `/help` 点击 `/panel` 时，runtime 会把原卡 message_id 作为更新目标

手工验收可按下面路径执行：

1. 在飞书里发送 `/panel`
2. 点击“会话”，确认卡片原地切到 `面板 · 会话`
3. 点击“总览”，确认回到原来的 panel 卡，而不是新增一条消息
4. 在 `/panel sessions` 或 `/resume list` 里点“下一页”，确认仍停留在同一张卡
5. 在 `/help` 里点“面板”，确认帮助卡原地切换成 panel 总览

## 后续 follow-up

- 如果后续要做更深层级子菜单，再评估是否需要显式 breadcrumb 或返回栈，而不是现在就提前引入复杂状态机。
- 如果飞书后续对消息更新能力有更多限制，再评估是否要把导航卡整体迁到 CardKit 常驻卡，而不是继续复用普通 interactive message 更新。
