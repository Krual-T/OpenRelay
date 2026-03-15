# Codex Thread First Runtime

更新时间：2026-03-15

## 目标

这份文档回答四个问题：

- openrelay 是否还应该保留“本地 session”作为用户可见会话身份
- 如果 Feishu 只是壳，运行时应该以什么为主身份建模
- 顶层消息里如果后续要执行 `ls` 这类 bash 命令，主路径应该怎么接
- 现有代码应按什么顺序收敛，才能避免继续叠加兼容层

这份文档只讨论目标模型、命令语义和迁移顺序，不讨论具体 patch。

## 结论

openrelay 应收敛到下面这条主线：

- **Codex thread 是唯一用户可见会话身份**
- **Feishu thread / 子 thread 只是 UI 作用域，不是会话真相**
- **本地状态只保留“scope 运行态”，不再保留“本地 session 历史”这个产品概念**
- **bash 执行能力与 Codex 对话身份解耦，作为独立的顶层执行通道存在**

也就是说，用户视角应该只看到两层：

- 当前这个 Feishu scope 绑定了什么运行配置
- 当前这个 Feishu scope 正在使用哪个 Codex thread

本地 `session_id`、本地 `/new`、本地 `/resume <local_session_id>` 这类语义，都不应继续暴露为主路径。

## 为什么需要继续收敛

当前仓库虽然已经把 `/resume` 和 `/compact` 切到了 Codex native thread，但运行时骨架仍然以本地 `SessionRecord` 为中心。

主要表现有三类：

- 配置命令仍然通过“创建下一个本地 session”实现，例如 `/clear`、`/model`、`/sandbox`、`/cwd`
- 顶层消息入口仍然先解析“本地 session 生命周期”，再决定是否绑定 Codex thread
- Codex app-server client 的复用键仍依赖 `session.session_id`，说明本地壳仍然参与了运行时身份

这会带来两个长期问题：

- **用户心智不自洽**：表面上说 Codex thread 才是真会话，内部却仍在不断长出新的本地 session 壳
- **主路径越来越脏**：每个命令都需要决定“是切 thread、切配置，还是再造一个 session”

继续隐藏 `session_id` 不够，应该直接把模型改掉。

## 目标模型

### 1. ScopeRuntimeState

每个 Feishu scope 只保留一份当前运行态。

建议字段：

- `scope_key`
- `backend`
- `cwd`
- `release_channel`
- `model_override`
- `safety_mode`
- `active_thread_id`
- `updated_at`

它表达的是：

- 当前 scope 里的默认工作目录是什么
- 当前 scope 后续消息要发到哪个 backend
- 当前 scope 现在绑定的是哪个 Codex thread

它**不是历史记录**，也不承担“恢复旧本地会话”的职责。

### 2. ThreadViewCache

Codex thread 的展示信息可以有本地缓存，但缓存不是事实来源。

建议字段：

- `thread_id`
- `name`
- `preview`
- `cwd`
- `updated_at`
- `status`

它只用于：

- `/resume list` 的本地展示加速
- `/panel`、`/status` 里的 thread 摘要

真正的 thread 历史、turn 记录、compact 结果都仍以 Codex app-server 为准。

### 3. ShellRuntimeState

如果后续支持顶层执行本地 bash，shell 运行态应单独建模，不应塞回会话身份层。

最小字段建议：

- `scope_key`
- `cwd`
- `env_profile`
- `updated_at`

是否需要长期持久化，可以后置决定。第一版甚至可以直接复用 `ScopeRuntimeState.cwd`，不单独落表。

## 用户可见语义

### 会话语义

用户只需要理解：

- “当前绑定 thread” 是真正的对话上下文
- `/resume` 是切换 Codex thread，不是恢复 openrelay 本地历史
- `/clear` 是解绑当前 thread，不是新建一个本地 session

### 配置语义

配置命令都应该是“原地修改当前 scope 配置”，而不是“新建一个继承旧状态的本地 session”。

这包括：

- `/cwd`
- `/model`
- `/sandbox`
- `/backend`
- `/main`
- `/develop`
- `/stable`

### 顶层子 thread 语义

如果 Feishu 子 thread 已经绑定到某个 Codex thread，就应继续固定绑定，不再允许在子 thread 内切换会话身份。

这样可以避免两类混乱：

- 同一个子 thread 一会儿在 A thread，一会儿又跳去 B thread
- 用户以为自己在“回复同一个上下文”，实际底层已经切了 thread

## 命令语义收敛

### 应保留的 openrelay 控制命令

- `/help`
- `/panel`
- `/status`
- `/usage`
- `/restart`
- `/stop`

它们属于运行时控制面，不依赖本地 session 历史是否存在。

### 应保留的 Codex thread 命令

- `/resume list`
- `/resume latest`
- `/resume <thread_id>`
- `/resume <index>`
- `/compact [thread_id]`

这些命令只面向 Codex native thread，不再接受本地 `session_id`。

### 应调整语义的命令

- `/clear`
  只清空 `active_thread_id`
- `/reset`
  重置整个 `ScopeRuntimeState` 到默认值
- `/cwd`
  原地更新 scope cwd；如果后续发新消息且当前未绑定 thread，则新 thread 从新 cwd 启动
- `/model`
  原地更新 scope model；不再制造新的本地壳
- `/sandbox`
  原地更新 scope sandbox
- `/backend`
  原地更新 scope backend；必要时清空 `active_thread_id`

### 应删除的用户语义

- `/new`
- `/resume <local_session_id>`
- “本地 session 列表是主要恢复入口”

这些语义与“Codex thread 是唯一会话身份”相冲突。

## 顶层 bash 执行能力

这是这次收敛里最容易被误做成歧义路由的部分。

结论很明确：

- **不要默认把裸文本 `ls` 当成 shell 命令**
- **shell 执行必须走显式通道**

### 为什么不能把裸 `ls` 直接判成 shell

因为它会破坏主路径稳定性。

存在三类歧义：

- 用户可能真的在问“ls 是什么意思”
- 用户可能希望 Codex 自己决定是否执行 `ls`
- 用户可能只是发了一个短 token，并不想触发本地命令

一旦系统默默把裸文本解释为 shell，用户就无法稳定预测“这条消息到底进入控制面、shell 面，还是对话面”。

### 建议主路径

顶层输入只保留三条明确路径：

1. `/...`
   进入 openrelay 控制命令
2. `/sh ...` 或 `! ...`
   进入本地 shell 执行
3. 其他普通文本
   进入 Codex thread 对话

这三条路径的好处是：

- 语义稳定
- 不需要猜测用户意图
- 不会污染 Codex thread 会话身份模型

### `/sh` 的职责边界

`/sh` 应只做一件事：在当前 scope 的 shell 运行态里执行本地命令，并把结果回给用户。

它不应：

- 改变当前绑定的 Codex thread
- 被记录成 Codex thread 历史
- 借用“创建本地 session”来表达执行上下文

### 是否要支持“裸 shell 意图识别”

如果未来真有需要，可以作为增强层追加，但不应作为主路径。

即使要做，也应该使用非常苛刻的规则，例如同时满足：

- 单行短文本
- 纯 ASCII
- 可被 shell 正常解析
- 首 token 在 allowlist 内，例如 `ls`、`pwd`、`cat`
- 不包含明显自然语言特征

即便如此，也只建议在用户明确开启某种 shell 模式后才生效，不建议默认开启。

## 对现有结构的影响

### `SessionRecord` 不应继续承担三种职责

当前 `SessionRecord` 同时承担了：

- scope 配置状态
- Codex thread 绑定
- 本地 session 历史节点

这是当前结构不稳定的根因。

目标上应把它拆开，至少在职责上拆开：

- 一个结构表达当前 scope 运行态
- 一个结构表达当前绑定的 thread 摘要
- 如有需要，再有一个独立结构表达 shell 运行态

### orchestrator 的锁键也应收敛

当前执行锁按 `session.session_id` 建模并不理想。

更稳定的方案是：

- 对话路径按 `scope_key` 或 `active_thread_id` 串行
- shell 路径按 `scope_key + shell` 串行

这样可以直接表达“同一个 scope 当前是否正在跑 Codex turn”以及“同一个 scope 当前是否正在跑本地 shell”。

### Codex client key 也应去本地 session 化

当前 client key 绑定 `session.session_id`，会放大本地壳的存在感。

目标上应切到更符合真实语义的键，例如：

- `codex_path + workspace_root + scope_key`
- 如果某些参数变化必须重建 client，再由 `model/sandbox/backend` 配置变化主动触发

不要再把“是否创建了新的本地 session”作为 client 生命周期的依据。

## 迁移顺序

这次收敛不适合一轮硬切，建议分三阶段推进。

### Phase 1：先统一用户语义

目标：

- 用户界面不再暴露本地 `session_id`
- `/resume` 只接受 Codex thread 目标
- `/clear`、`/model`、`/cwd` 等文案改成“修改当前 scope 配置”

完成标志：

- help、panel、status、README、命令回复里不再把本地 session 当主语义

### Phase 2：再收敛状态模型

目标：

- 引入 `ScopeRuntimeState`
- 让配置命令变成原地修改，而不是 `create_next_session()`
- 把“当前绑定 thread”作为 scope 状态，而不是 session 历史节点

完成标志：

- `session/mutations.py` 不再通过“创建下一个 session”表达配置变化
- `session/lifecycle.py` 不再把本地 session 历史作为主入口模型

### Phase 3：最后切运行时主路径

目标：

- orchestrator、execution key、active run、backend client key 去本地 session 化
- 明确加入 shell 执行通道，例如 `/sh`

完成标志：

- runtime 主路径只围绕 `scope_key`、`active_thread_id`、shell execution key 运转
- 对话和 shell 成为两条清晰并列的执行路径

## 不建议的方案

下面这些做法看起来像“平滑兼容”，但实际上会持续制造结构负担：

- 继续保留 `/resume <local_session_id>` 作为隐藏兜底
- 继续让配置命令通过“新建本地 session”实现
- 在顶层把裸 `ls` 自动解释为 shell
- 把 shell 执行记录塞进 Codex thread 历史，或者反过来用 shell 运行态冒充会话身份

这些做法的共同问题是：它们都在延缓模型收敛，而不是推动模型收敛。

## 建议的最小落地顺序

如果只选一条最短可执行路径，我建议是：

1. 删除剩余本地 session 用户语义，包括 `/resume <local_session_id>` fallback
2. 引入 `ScopeRuntimeState`，把 `/clear`、`/cwd`、`/model`、`/sandbox` 改成原地修改
3. 把 runtime 锁键和 Codex client key 从 `session.session_id` 切到 `scope_key`
4. 在此基础上再补 `/sh`，而不是提前引入裸 shell 识别

这样做的原因很直接：

- 先把身份模型收干净
- 再加 bash 通道时，才不会被旧 session 语义拖住

## 关闭条件

这份设计真正落地时，至少应满足下面条件：

- `/resume` 与 `/compact` 完全只面向 Codex thread
- 用户可见界面里不再把本地 session 当作恢复入口
- 配置命令不再通过派生新 session 实现
- runtime 锁键与 backend client 生命周期不再依赖本地 `session_id`
- 顶层 shell 通道采用显式语法，不引入裸文本歧义

在这些条件满足之前，本方案只算方向已确定，不算实现已完成。
