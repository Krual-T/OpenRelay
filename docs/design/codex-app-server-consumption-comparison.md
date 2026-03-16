# Codex 应用服务消费链路对比

更新时间：2026-03-16

## 这份文档要解决什么问题

上一版文档更像“架构结论”，但如果你真正想追实际细节，只知道“谁调用了谁”是不够的。

看一条调用链，真正有价值的通常不是：

- 图上画了多少个框
- 有没有提到应用服务（app-server）

而是下面这些更具体的问题：

1. 第一个真正发请求的地方在哪里？
2. 请求发的是什么方法（method）和参数（params）？
3. 回来的不是最终答案时，中间事件是怎么流动的？
4. 哪一层把原始协议翻译成内部状态？
5. 哪一层保存“这次会话是谁、这次回合是谁、现在是否在等待审批”？
6. 哪一层决定展示什么，而不是只转发原始数据？
7. 如果要改行为，应该改哪一层，才不会把结构弄乱？

这份文档按这个思路来整理。

## 先给你一个“看链路时该盯什么”的阅读提纲

如果你还不确定自己到底想看什么，可以先从下面 6 个关注点里挑。

### 1. 请求入口

你想知道“用户一句话最终是怎么进入 `codex app-server` 的”，就看：

- 谁第一次从业务对象组装出远程过程调用（RPC，Remote Procedure Call）参数
- 是先 `thread/start`，还是先 `thread/resume`
- `turn/start` 是谁发的

这类问题的关键词是：

- “谁发请求”
- “请求体长什么样”
- “什么时候决定 `threadId`”

### 2. 事件回流

你想知道“为什么还没结束时界面就已经在更新”，就看：

- 谁订阅了通知（notification）
- 谁接收了服务端请求（server request）
- 流式增量（delta）怎样一步步变成界面上的部分文本

这类问题的关键词是：

- “谁收事件”
- “谁处理流式输出”
- “审批请求是怎么插进来的”

### 3. 状态归约

你想知道“为什么上层代码不用关心 `item/agentMessage/delta` 这种协议细节”，就看：

- 原始协议在哪一层被翻译
- 翻译后的内部事件长什么样
- 内部状态模型是谁维护的

这类问题的关键词是：

- “协议翻译”
- “统一事件”
- “状态模型”

### 4. 展示输入

你想知道“展示层到底消费什么”，就看：

- 展示层拿到的是原始协议，还是已经整理过的视图模型（view model）
- 文本、命令、推理、审批是不是被统一表示了

这类问题的关键词是：

- “展示层输入”
- “卡片怎么刷新”
- “最终回复从哪里来”

### 5. 交互闭环

你想知道“审批、停止、补充输入这些交互能不能走通”，就看：

- 服务端请求（server request）有没有真正被接住
- 接住以后有没有等待用户决策
- 用户决策有没有再写回应用服务（app-server）

这类问题的关键词是：

- “审批闭环”
- “停止怎么生效”
- “用户输入如何回写”

### 6. 修改边界

你想知道“以后要改某个行为应该改哪”，就看：

- 是协议适配层问题
- 还是运行时服务层问题
- 还是展示层问题

这类问题的关键词是：

- “哪一层负责什么”
- “改这里会不会影响别层”

## 一张最实用的总图

如果你只想先抓住主路径，不想一上来就看太多细节，可以先看这张图。

```mermaid
flowchart TD
  A[用户消息]
  B[业务入口]
  C[会话与回合执行]
  D[应用服务请求<br/>thread/start resume turn/start]
  E[应用服务事件回流<br/>started delta completed requestApproval]
  F[协议翻译]
  G[统一状态]
  H[展示刷新]

  A --> B --> C --> D --> E --> F --> G --> H
```

真正要读细节时，不要只问“有没有这 8 层”，而要问：

- `D` 这一层到底发了什么
- `E` 这一层到底收到了什么
- `F` 这一层到底丢掉了什么协议细节，保留了什么内部语义
- `G` 这一层到底存了哪些状态

下面分两条链路展开。

## Openrelay 现在的实际消费链路

### 一句话结论

`openrelay` 现在已经把 `codex app-server` 当成正式后端来消费，但它的上层并不直接依赖原始协议，而是依赖翻译后的统一运行时事件（RuntimeEvent）和实时视图模型（LiveTurnViewModel）。

这句话拆开以后，真正要看的细节是 4 件事：

1. 请求在哪里发
2. 事件在哪里收
3. 协议在哪里翻译
4. 展示状态在哪里生成

## Openrelay：从入口到请求发出

### 第一个业务入口

用户消息先进入：

- `src/openrelay/runtime/orchestrator.py`

这里的职责不是直接跟 `app-server` 说话，而是先做业务层控制：

- 过滤无效消息
- 解析会话（session）
- 决定是不是停止命令
- 控制串行执行

换句话说，这一层解决的是“这条消息该不该跑、属于哪个会话”，还没有进入“怎么调应用服务”。

### 真正进入执行主路径的地方

随后进入：

- `src/openrelay/runtime/turn.py`

这里的 `BackendTurnSession.run_with_agent_runtime()` 才真正把这次用户输入包装成回合输入（TurnInput），交给统一运行时服务（AgentRuntimeService）。

你如果想追“这次用户输入是从哪里变成后端输入对象的”，这里就是第一个关键点。

### 真正发应用服务请求的地方

再往下是：

- `src/openrelay/agent_runtime/service.py`
- `src/openrelay/backends/codex_adapter/backend.py`
- `src/openrelay/backends/codex_adapter/client.py`

真正开始发 `thread/start`、`thread/resume`、`turn/start` 的，不是 `RuntimeOrchestrator`，也不是展示层，而是 `CodexSessionClient`。

这里可以把职责拆清楚：

- `CodexRuntimeBackend`：统一后端接口到 Codex 适配器的桥
- `CodexSessionClient`：真正决定发哪些应用服务方法
- `CodexRpcTransport`：真正把请求送到底层客户端

### 这里最值得看的实际细节

#### 细节 1：什么时候 `thread/start`

在 `CodexSessionClient._ensure_thread()` 里：

- 如果已有原生会话标识（native session id），就发 `thread/resume`
- 如果没有，就发 `thread/start`

这决定了它是“续接旧对话”还是“创建新对话”。

#### 细节 2：`turn/start` 的参数是谁组的

在 `CodexProtocolMapper.build_turn_start_params()` 里，会把这些信息装进请求：

- `threadId`
- `cwd`（当前工作目录，current working directory）
- `approvalPolicy`（审批策略）
- `model`（模型）
- `input`（输入）

也就是说，协议参数的装配不是散落在各处，而是集中在协议映射器（ProtocolMapper）里。

#### 细节 3：会话标识什么时候落库

如果这是新线程，`_ensure_thread()` 拿到 `thread/start` 的结果后，会立刻发一个会话已启动事件（SessionStartedEvent）。  
上层再把这个原生会话标识持久化。

这一步很重要，因为后续 stop、resume、read transcript 都依赖这个标识。

## Openrelay：事件是怎么回来的

### 事件订阅在哪里挂上去

在 `CodexSessionClient.start_turn()` 里，会注册两类订阅：

- 通知订阅（notification subscriber）
- 服务端请求订阅（server request subscriber）

然后把它们都交给：

- `CodexTurnStream`

这说明 `CodexTurnStream` 是这条链上的“事件汇流点”。

### `CodexTurnStream` 真正在做什么

文件：

- `src/openrelay/backends/codex_adapter/turn_stream.py`

这里有 3 个实际很重要的动作。

#### 动作 1：处理通知

`handle_notification()` 会做两件事：

1. 调用 `mapper.map_notification()`，把原始协议通知翻译成内部事件
2. 把翻译后的事件逐个发布给运行时事件汇流器（event hub）

这里顺手还会处理回合结束条件：

- 如果收到了回合完成（turn.completed），就结束 future
- 如果收到了回合中断（turn.interrupted），就抛出中断
- 如果收到了回合失败（turn.failed），就抛出错误

也就是说，这一层不只是“转发事件”，还负责“判断这次回合什么时候算结束”。

#### 动作 2：处理服务端请求

`handle_server_request()` 的流程是：

1. 调用 `mapper.map_server_request()`
2. 把服务端请求翻译成审批请求事件（ApprovalRequestedEvent）
3. 先发布给上层
4. 等上层把用户决策写回来
5. 再调用 `transport.send_result()` 回给应用服务

这一步就是完整的交互闭环。

#### 动作 3：处理中断

`interrupt()` 会在知道 `turn_id` 以后发：

- `turn/interrupt`

这意味着 stop 不是单纯把本地任务杀掉，而是明确通知应用服务中断当前回合。

## Openrelay：原始协议是怎么被翻译掉的

### 真正的协议翻译层

文件：

- `src/openrelay/backends/codex_adapter/mapper.py`

如果你想知道“哪些应用服务方法会影响界面”，这里是最该细读的文件。

它把原始方法映射成统一运行时事件（RuntimeEvent）。下面是最关键的一组对照：

| 原始应用服务方法 | 中文含义 | 内部事件 |
| --- | --- | --- |
| `thread/started` | 线程已启动 | `session.started` |
| `turn/started` | 回合已启动 | `turn.started` |
| `item/agentMessage/delta` | 助手消息增量 | `assistant.delta` |
| `item/reasoning/textDelta` | 推理文本增量 | `reasoning.delta` |
| `item/commandExecution/outputDelta` | 命令输出增量 | `tool.progress` |
| `item/started` | 某个条目开始 | `tool.started` 或其他内部事件 |
| `item/completed` | 某个条目完成 | `assistant.completed` / `tool.completed` |
| `turn/completed` | 回合结束 | `turn.completed` / `turn.interrupted` / `turn.failed` |
| `item/commandExecution/requestApproval` | 命令审批请求 | `approval.requested` |

### 为什么这一层重要

因为它决定了两件事：

1. 上层“看得见什么”
2. 上层“看不见什么”

例如展示层并不需要知道：

- 某条协议方法原始字段名是 `contentIndex` 还是 `summaryIndex`
- 某条输出来自 `item/agentMessage/delta` 还是兼容别名

这些都在协议映射器（mapper）里被消化掉了。

## Openrelay：状态在哪里成形

### 统一状态归约在什么地方

文件：

- `src/openrelay/agent_runtime/service.py`

运行时服务（AgentRuntimeService）收到统一运行时事件（RuntimeEvent）后，会把它们交给实时回合注册表（LiveTurnRegistry）去归约。

这里可以把“归约”理解成：

- 之前状态是什么
- 新来一个事件以后
- 现在状态变成什么

### 展示层真正消费的不是协议，而是状态

文件：

- `src/openrelay/presentation/live_turn.py`

展示层最后消费的是实时视图模型（LiveTurnViewModel），不是原始应用服务事件。

它关心的字段是：

- 当前助手文本
- 当前推理文本
- 当前工具列表
- 当前审批请求
- 当前状态是运行中、完成、失败还是中断

所以如果你问“为什么 Feishu 卡片不用知道 `item/agentMessage/delta` 这些名字”，答案就是：这些细节在更下面已经被翻译过了。

## Openrelay：一条最具体的例子

这里用“用户发一句话，助手开始流式输出，然后申请命令审批”举例。

### 这条链路实际发生了什么

1. `RuntimeOrchestrator` 收到 Feishu 消息
2. `BackendTurnSession` 组装回合输入（TurnInput）
3. `CodexSessionClient` 先确保线程存在：已有就 `thread/resume`，没有就 `thread/start`
4. `CodexSessionClient` 发 `turn/start`
5. 应用服务开始回推通知：
   - `turn/started`
   - `item/agentMessage/delta`
   - `item/commandExecution/requestApproval`
6. `CodexTurnStream` 收到这些事件
7. `CodexProtocolMapper` 把它们翻译成：
   - `turn.started`
   - `assistant.delta`
   - `approval.requested`
8. `AgentRuntimeService` 归约出新的实时视图模型（LiveTurnViewModel）
9. `LiveTurnPresenter` 把它变成卡片快照
10. 用户在 Feishu 上点同意或拒绝
11. 上层把审批决定回写给 `CodexTurnStream.resolve_approval()`
12. `CodexTurnStream` 再把结果发回应用服务

如果你要查“审批为什么没弹出来”或者“审批点了以后为什么没继续”，这 12 步已经足够你定位问题。

## Codex CLI 的终端界面现在怎么消费应用服务

### 一句话结论

截至 2026-03-16，官方 `codex cli` 的终端界面（TUI，Text User Interface，文本用户界面）已经把应用服务客户端（InProcessAppServerClient）接进主循环，但当前主界面仍主要由直接核心事件流（direct-core event stream）驱动。

所以它不是：

- 完全没接应用服务

也不是：

- 已经完全靠应用服务驱动

而是：

- 正在迁移中的混合态

## Codex CLI：现在实际有哪两条事件路

### 路 1：应用服务事件路

在官方 `app.rs` 里，主循环已经监听：

- `app_server.next_event()`

这说明应用服务事件流已经被接进来了。

### 路 2：直接核心事件路

同一个主循环里，还在监听：

- `thread_manager.subscribe_thread_created()`

并且在线程创建后，会继续：

- `self.server.get_thread(thread_id)`
- `thread.next_event().await`

然后把事件送进：

- `AppEvent::ThreadEvent`

这说明当前主界面依然深度依赖直接核心事件流。

## Codex CLI：为什么说它还没真正“消费”应用服务

### 关键不是“有没有监听”，而是“监听后做了什么”

官方当前文件：

- `codex-rs/tui/src/app/app_server_adapter.rs`

这里写得非常直白：这是混合迁移阶段（hybrid migration period）的临时适配层。

当前逻辑是：

- `ServerNotification`：忽略
- `LegacyNotification`：忽略
- `ServerRequest`：直接拒绝

这意味着：

- 应用服务事件流已经接进来
- 但它还没有真正进入当前主界面的状态更新主路径

如果你问“那它现在接进来干嘛”，答案更接近：

- 为迁移铺底
- 让应用服务成为未来统一入口
- 但当前版本还没完全把旧路径拆掉

## Codex CLI：一条最实际的追踪方式

如果你要追官方 TUI 现在到底谁在改界面，不要先看抽象架构图，先看这 4 个问题：

1. 主循环在 `select!` 里监听了哪些输入源？
2. 应用服务来的事件最后有没有改 `App` 或 `ChatWidget` 状态？
3. `thread.next_event()` 来的事件最后有没有改 `App` 或 `ChatWidget` 状态？
4. 审批请求（request approval）到底是被处理了，还是被拒绝了？

按这个标准去看，当前答案是：

- 应用服务事件：接进来了，但大部分还没转成界面状态
- 直接核心事件：仍然是主界面事实来源
- 审批服务端请求：当前适配层里直接拒绝

## 两条链路的核心差异

| 关注点 | openrelay | codex cli 终端界面（截至 2026-03-16） |
| --- | --- | --- |
| 应用服务角色 | 正式主后端 | 已接入，但仍在迁移 |
| 第一个真正发 RPC 的位置 | `CodexSessionClient` | 正在从旧路径迁到应用服务路径 |
| 谁收通知和服务端请求 | `CodexTurnStream` | 主循环能收到，但当前适配层基本不消费 |
| 谁翻译协议 | `CodexProtocolMapper` | 当前主路径仍更多依赖旧事件模型 |
| 展示层最终消费什么 | 实时视图模型（LiveTurnViewModel） | `AppEvent`、`EventMsg`、`ChatWidget` 状态 |
| 审批是否闭环 | 是 | 当前适配层不是闭环，而是拒绝请求 |
| 主界面事实来源 | 应用服务协议翻译后的统一状态 | 仍偏向直接核心事件流 |

## 如果你后面还想继续深挖，最值得问的 10 个具体问题

下面这些问题都比“调用链是什么”更容易落到代码。

1. 新会话和旧会话分别在哪一行代码决定走 `thread/start` 还是 `thread/resume`？
2. `turn/start` 的 `input` 是怎么从用户消息拼出来的？
3. 图片输入在进入应用服务前有没有被重写？
4. 哪一种原始协议方法会变成“界面上的部分回复”？
5. 哪一种原始协议方法会变成“工具执行中”？
6. 命令审批请求从应用服务来到 Feishu，中间经过了哪些对象？
7. 用户点同意以后，结果是在哪一层写回应用服务的？
8. stop 命令是只停本地任务，还是会发 `turn/interrupt`？
9. 终端界面当前到底有没有真正把 `ServerNotification` 转成 UI 状态？
10. 哪些地方现在看起来像“兼容过渡层”，以后应该删掉？

如果后面你说不清需求，可以直接用这种句式问：

- “我想看 `turn/start` 的参数是谁拼的”
- “我想看审批请求从应用服务到 Feishu 的完整路径”
- “我想看终端界面现在为什么还不算真正消费了应用服务”
- “我想看 stop 命令最终是不是发了 `turn/interrupt`”
- “我想看实时回复文本是由哪几个原始事件拼起来的”

这样问题就会立刻从“空泛架构讨论”变成“可验证的代码追踪”。

## 证据

### openrelay 仓库内代码

- `src/openrelay/runtime/orchestrator.py`
- `src/openrelay/runtime/turn.py`
- `src/openrelay/agent_runtime/service.py`
- `src/openrelay/backends/codex_adapter/backend.py`
- `src/openrelay/backends/codex_adapter/client.py`
- `src/openrelay/backends/codex_adapter/transport.py`
- `src/openrelay/backends/codex_adapter/turn_stream.py`
- `src/openrelay/backends/codex_adapter/mapper.py`
- `src/openrelay/presentation/live_turn.py`

### 官方外部资料

- `codex app-server` README  
  <https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md>
- 终端界面应用服务适配层  
  <https://github.com/openai/codex/blob/main/codex-rs/tui/src/app/app_server_adapter.rs>
- 终端界面主循环  
  <https://github.com/openai/codex/blob/main/codex-rs/tui/src/app.rs>
- 开放拉取请求（PR，Pull Request）：`feat(tui): migrate TUI to in-process app-server`  
  <https://github.com/openai/codex/pull/14018>
- 开放拉取请求（PR，Pull Request）：`feat(tui): route fresh-session thread lifecycle through app-server`  
  <https://github.com/openai/codex/pull/14699>
- 开放拉取请求（PR，Pull Request）：`feat(tui): route resume and fork thread lifecycle through app-server, eliminating DirectCore transport`  
  <https://github.com/openai/codex/pull/14711>
- 开放拉取请求（PR，Pull Request）：`Move TUI on top of app server (parallel code)`  
  <https://github.com/openai/codex/pull/14717>

## 时效性说明

- `codex cli` 终端界面的结论，基于 2026-03-16 查询到的官方 `main` 分支源码与当日仍为打开状态（open）的拉取请求（PR）。
- 由于官方这一段正在快速迁移，后续如果这些 PR 合并，本文对终端界面现状的描述可能会失效。
- `openrelay` 部分结论基于当前仓库代码，时效点同样是 2026-03-16。
