# openrelay 架构图

更新时间：2026-03-16

本文按当前仓库实现整理 `openrelay` 的运行时结构。重点不是历史设计目标，而是代码里已经存在的主路径、分层和依赖关系。

## 总览

```mermaid
flowchart TB
    User[Feishu 用户]
    Feishu[Feishu 平台]
    Server[FastAPI Server\nopenrelay.server]
    Dispatcher[FeishuEventDispatcher\n解析消息 / 卡片动作]
    Messenger[FeishuMessenger\n发送文本 / 卡片 / 下载图片]
    Runtime[RuntimeOrchestrator\n主调度入口]

    Commands[RuntimeCommandRouter\n/panel /resume /cwd /help ...]
    Exec[RuntimeExecutionCoordinator\n串行锁 / follow-up 队列]
    Reply[ReplyPolicy + Streaming\n回复路由 / typing / CardKit]

    SessionLayer[Session Services\nscope / lifecycle / browser /\nworkspace / shortcut / mutation]
    Presentation[Presentation\npanel / session / status]
    Storage[(StateStore SQLite\nsessions / messages /\naliases / shortcuts / dedup)]
    Binding[(SessionBindingStore\nrelay_session_bindings)]
    Release[ReleaseCommandService\nmain / develop 切换]

    AgentRuntime[AgentRuntimeService\n统一会话 / turn / approval 语义]
    RuntimeBackend[CodexRuntimeBackend\napp-server runtime adapter]
    Codex[CodexAppServerClient\ncodex app-server]

    User --> Feishu
    Feishu --> Server
    Server --> Dispatcher
    Server --> Messenger
    Dispatcher --> Runtime
    Runtime --> Commands
    Runtime --> Exec
    Runtime --> Reply
    Runtime --> SessionLayer
    Runtime --> Presentation
    Runtime --> Release
    Runtime --> Storage
    Runtime --> Binding
    Runtime --> AgentRuntime

    SessionLayer --> Storage
    Presentation --> Storage
    AgentRuntime --> Binding
    AgentRuntime --> RuntimeBackend
    RuntimeBackend --> Codex
    Reply --> Messenger
    Runtime --> Messenger
    Messenger --> Feishu
```

## 主路径

```mermaid
sequenceDiagram
    participant U as Feishu User
    participant F as Feishu
    participant D as FeishuEventDispatcher
    participant R as RuntimeOrchestrator
    participant S as Session/State Layer
    participant E as ExecutionCoordinator
    participant A as AgentRuntimeService
    participant B as CodexRuntimeBackend
    participant C as codex app-server
    participant M as FeishuMessenger

    U->>F: 发送消息 / 卡片动作
    F->>D: webhook 或 websocket event
    D->>D: 解析消息, 下载图片资源
    D->>R: dispatch_message(...)
    R->>S: 解析 scope / 加载或创建 session
    R->>E: 检查串行锁与 follow-up 队列
    alt 本地命令
        R->>S: 执行 /panel /resume /cwd /help 等命令
        R->>M: 发送文本或交互卡片
    else 普通消息
        R->>A: run_turn(...)
        A->>B: start_turn(...)
        B->>C: turn/start + 后续协议请求
        C-->>B: delta / tool / approval / completed
        B-->>A: 统一 RuntimeEvent
        A-->>R: live turn state
        R->>M: 流式文本 / typing / 最终卡片
    end
    M-->>F: reply / update
    F-->>U: 在 thread 中看到结果
```

## 当前分层说明

- `server` 层负责启动 `FastAPI`、装配 `StateStore`、`FeishuMessenger`、`RuntimeOrchestrator`，并根据 `FEISHU_CONNECTION_MODE` 决定走 webhook 还是 websocket。
- `feishu` 层负责外部平台适配：事件解析、消息资源下载、文本与交互卡片发送，不承载 runtime 语义。
- `runtime` 层是主调度中枢，负责命令分流、执行串行化、follow-up 合并、回复策略、流式状态和重启/帮助/panel 等产品行为。
- `session` + `storage` 层负责本地状态：session 指针、消息摘要、scope alias、目录快捷方式，以及 relay session 到 backend native session 的绑定关系。
- `agent_runtime` 层把 provider-specific 协议收敛成统一的 session / turn / approval 语义；当前内置实现是 `CodexRuntimeBackend`。
- `backends` 层现在主要承担 provider transport / adapter 职责；当前默认执行路径已经统一收敛到 `CodexRuntimeBackend -> CodexAppServerClient`。
- `presentation` 层只负责把 session、panel、status 等状态投影成 Feishu 卡片或文本，不直接理解底层 provider 协议。

## 关键目录

- `src/openrelay/server.py`：应用装配与进程入口
- `src/openrelay/feishu/`：Feishu 接入、消息解析、发送与流式卡片
- `src/openrelay/runtime/`：主调度、命令路由、执行协调、回复策略
- `src/openrelay/session/`：session scope、workspace、resume、binding
- `src/openrelay/storage/`：SQLite 状态存储
- `src/openrelay/agent_runtime/`：统一 runtime 事件、模型、reducer、service
- `src/openrelay/backends/`：provider adapter 与 `codex app-server` 客户端
- `src/openrelay/presentation/`：Feishu 面板与状态展示

## 当前结构特征

- 对外产品入口已经统一成 `Feishu -> RuntimeOrchestrator`。
- 对内 provider 接入已经以 `agent runtime` 为唯一主路径收敛。
- 持久化分成两类：
  - `StateStore` 保存本地产品状态与轻量上下文。
  - `SessionBindingStore` 保存 relay session 与 backend native session 的绑定。
- 回复链路和执行链路已明确分离：
  - 执行侧处理 session、turn、approval、串行化。
  - 回复侧处理 thread 路由、typing、CardKit streaming 和最终消息落点。
