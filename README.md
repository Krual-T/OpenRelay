<div align="center">
  <img src="static/openrelay_logo.png" alt="OpenRelay logo" width="220" />

# openrelay

### 把你的 coding agent，接进飞书。

让 `Codex` 真正以“远程工作台”的方式进入飞书：保留原生 session、支持 thread 内连续追问、可切换工作区，并把流式执行过程稳定投影回聊天界面。

<p>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-111111?style=flat-square&logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-openrelay-111111?style=flat-square&logo=fastapi&logoColor=white">
  <img alt="Feishu" src="https://img.shields.io/badge/Feishu-chat%20native-111111?style=flat-square">
  <img alt="Codex" src="https://img.shields.io/badge/Codex-app--server-111111?style=flat-square">
</p>
</div>

## 这项目是干什么的

大多数“聊天接代码”的工具，一旦任务变复杂，就会迅速露出原形：

- session 不是真续接，只是在重复喂 prompt
- 聊天壳和 agent runtime 混在一起，行为不可控
- 切目录、切工作区后，上下文很容易乱掉
- 长任务在 IM 里几乎不可读，也不可追踪

`openrelay` 想做的是另一条路：

把飞书变成一个真正可用的 coding-agent 远程控制面板，而不是一个演示味很重的“问答机器人”。

它当前的主线能力是：

- 直接续接真实 backend thread，而不是伪造“上下文连续”
- 让 Feishu thread 和本地 agent session 形成稳定绑定
- 在 `main` / `develop` 工作区之间明确切换
- 把运行中状态、流式输出、最终答复投影回飞书
- 在内部保持 backend-neutral runtime，不把产品绑死在单一 provider 上

目前主线路径是 `Codex app-server`；`Claude` 适配器已经接进同一套 runtime 形状，但还只是最小实现。

## 为什么它会和别的 bot 不一样

### 1. 它真的尊重 session
`/resume` 绑定的是 backend 原生会话，不是“再发一遍历史消息”。

这意味着 `openrelay` 的连续性不是文案层面的连续，而是运行时层面的连续。

### 2. 它以 thread-first 方式工作
在飞书里，你可以直接在线程里继续追问、补充信息、停止当前运行，再让下一轮 follow-up 接着处理，而不是每次都从头开聊。

### 3. 它把工作区切换当成一等能力
通过 `/main`、`/stable`、`/develop`、`/cwd` 和快捷目录，agent 可以在不同工作树之间切换，而不会把 session 状态搅成一团。

### 4. 它的 runtime 是分层的
`feishu`、`runtime`、`agent_runtime`、`backends`、`storage/session` 职责分离，后续演进不会因为某个 CLI 变化而整套产品一起塌。

### 5. 它是按“长任务真的能跑”来设计的
流式回复、typing、session 串行、follow-up 合并、命令分流、本地状态持久化，都是主路径，不是补丁功能。

## 你能直接拿到什么

- Feishu webhook / WebSocket 两种接入模式
- 流式卡片回复与最终态收口
- `/panel` 总入口，统一查看 sessions / directories / commands / status
- relay session 到 backend native session 的绑定能力
- 飞书图片消息转发进 coding-agent 输入链路
- 基于 SQLite 的本地状态存储：sessions、aliases、dedup、shortcuts、bindings
- `/health` 健康检查接口

## 架构一眼看懂

`openrelay` 当前可以概括为五层：

1. `feishu/`：平台接入、卡片、typing、streaming
2. `runtime/`：命令分流、会话编排、执行主路径
3. `agent_runtime/`：backend-neutral 的 turn / event / approval / transcript 语义
4. `backends/`：Codex、Claude 等 provider adapter
5. `storage/` + `session/`：SQLite 状态与 relay-to-backend 绑定

完整拆解可看 `docs/architecture.md`。

## 快速开始

### 1. 安装依赖

```bash
uv sync --extra dev
```

### 2. 复制环境变量

```bash
cp .env.example .env
```

最少先配这些：

```env
PORT=3000
DATA_DIR=./data
WORKSPACE_DIR=/absolute/path/to/your/workspace
MAIN_WORKSPACE_DIR=/absolute/path/to/main/worktree
DEVELOP_WORKSPACE_DIR=/absolute/path/to/develop/worktree

FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_CONNECTION_MODE=websocket
FEISHU_BOT_OPEN_ID=ou_xxx
FEISHU_STREAM_MODE=card

MODEL_BACKEND=codex-cli
CODEX_CLI_PATH=codex
CODEX_SANDBOX=workspace-write
CODEX_SESSIONS_DIR=~/.codex/sessions
```

说明：

- `websocket` 是默认模式，此时 `openrelay` 只绑定 `127.0.0.1`
- webhook 模式会注册 `WEBHOOK_PATH`，并监听 `0.0.0.0`
- `CODEX_SQLITE_HOME` 可把 relay 驱动的 Codex state 与日常交互式 Codex home 隔离
- `FEISHU_ALLOWED_OPEN_IDS` 与 `FEISHU_ADMIN_OPEN_IDS` 可增加应用侧权限控制

### 3. 启动服务

```bash
uv run openrelayd
```

### 4. 检查健康状态

```bash
curl http://127.0.0.1:3000/health
```

### 5. 接入飞书

- 如果 `FEISHU_CONNECTION_MODE=websocket`，在飞书开放平台开启长连接接收即可，不需要 webhook URL。
- 如果 `FEISHU_CONNECTION_MODE=webhook`，把飞书事件订阅地址指向：

```text
http://your-host:3000/feishu/webhook
```

## 命令面

### 会话与导航
- `/panel [sessions|directories|commands|status]`
- `/resume [latest|thread_id|local_session_id]`
- `/compact [thread_id|local_session_id]`
- `/status`
- `/help`

### 工作区控制
- `/main [reason]`
- `/stable [reason]`
- `/develop [reason]`
- `/cwd [path]`
- `/cd [path]`
- `/shortcut list|add|remove|cd`

### 运行控制
- `/stop`
- `/clear`
- `/model [name|default]`
- `/sandbox [read-only|workspace-write|danger-full-access]`
- `/backend [list|name]`
- `/ping`
- `/restart`（仅管理员）

## 推荐使用方式

1. 在飞书里从 `/panel` 或一条直接任务消息开始。
2. 让 `openrelay` 把当前 scope 绑定到 backend session。
3. 同一任务就在 thread 里持续补充，而不是反复重讲背景。
4. 需要回到旧会话时，用 `/resume` 接回原生 agent thread。
5. 需要切执行面时，用 `/main`、`/develop` 或 `/cwd`。

核心理念只有一句话：

飞书只是控制面，backend session 必须是真的。

## 当前 backend 状态

### Codex
- 当前一等主路径
- 通过 `codex app-server` 接入
- 原生 session 续接已经是产品主流程的一部分

### Claude
- 已有 adapter
- 目前仍是最小实现，还没有和 Codex 做完整能力对齐

## 本地开发

```bash
uv run pytest
```

建议优先阅读这些入口：

- `src/openrelay/server.py`
- `src/openrelay/runtime/orchestrator.py`
- `src/openrelay/agent_runtime/service.py`
- `src/openrelay/backends/codex_adapter/`
- `docs/architecture.md`

## 为什么这个项目值得关注

因为“在聊天软件里远程驱动 coding agent”这件事，只有在下面这些点都成立时才真正有用：

- session 身份是真实的
- 执行位置是明确的
- follow-up 是连续的
- 流式输出是可读的
- 工作区边界是清楚的

这就是 `openrelay` 的判断。

如果你不想要一个只能 demo 的 bot，而是想要一个能在真实开发任务里活下来的远程 agent 入口，这个仓库就是为这个方向做的。
