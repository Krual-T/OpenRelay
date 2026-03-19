<div align="center">
  <img src="static/openrelay_logo.png" alt="OpenRelay logo" width="220" />

### OpenRelay——把你的 coding agent，接进飞书。

让 `Codex` 真正以“远程工作台”的方式进入飞书：保留原生 session、支持 thread 内连续追问、可按目录切换不同项目上下文，并把流式执行过程稳定投影回聊天界面。

Connect your local coding agent to Feishu with real backend sessions, thread-first follow-ups, and per-directory project context.

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
- 切目录、切项目后，上下文和能力边界很容易乱掉
- 长任务在 IM 里几乎不可读，也不可追踪

`openrelay` 想做的是另一条路：

把飞书变成一个真正可用的 coding-agent 远程控制面板，而不是一个演示味很重的“问答机器人”。

它当前的主线能力是：

- 直接续接真实 backend thread，而不是伪造“上下文连续”
- 让 Feishu thread 和本地 agent session 形成稳定绑定
- 按目录切换不同项目，并保留各自独立的 agent 定义与能力边界
- 把运行中状态、流式输出、最终答复投影回飞书
- 在内部保持 backend-neutral runtime，不把产品绑死在单一 provider 上

目前主线路径是 `Codex app-server`；`Claude` 适配器已经接进同一套 runtime 形状，但还只是最小实现。

## 它不是另一个 OpenClaw 壳层

很多人第一反应会把这类产品和 OpenClaw 风格方案放在一起看，但 `openrelay` 的判断不一样。

OpenClaw 类方案的优点是“开箱即用、界面像一个完整产品”，但代价通常也很明显：

- 它往往自带一整套自己的 agent 壳、交互壳和产品约束
- 你需要接受它定义好的工作流、呈现方式和能力边界
- 一旦你已经在本机把 Codex 打磨出了自己的目录结构、技能、提示词和项目约定，这些沉淀很容易被包在外壳里，不能原样复用

`openrelay` 走的是另一条路：

- 不重做一个“替你定义 agent”的平台
- 不试图覆盖你本机已经存在的 Codex 使用方式
- 重点是把你已经调好的本地 Codex，会话级、目录级、项目级地接进飞书

如果你本来就熟悉怎么自定义 Codex，这一点会特别有价值。

## 为什么它会和别的 bot 不一样

### 1. 它真的尊重 session

`/resume` 绑定的是 backend 原生会话，不是“再发一遍历史消息”。

这意味着 `openrelay` 的连续性不是文案层面的连续，而是运行时层面的连续。

### 2. 它以 thread-first 方式工作

在飞书里，你可以直接在线程里继续追问、补充信息、停止当前运行，再让下一轮 follow-up 接着处理，而不是每次都从头开聊。

### 3. 它允许你按目录“切换不同的 Codex agent”

`openrelay` 本身不替你重新发明 agent 定义。

它真正提供的能力是：把你电脑上不同目录里的 Codex 配置、项目约定、技能和工作方式，作为真实执行环境接进飞书。

这意味着只要你熟悉如何定制 Codex，你就可以让不同项目天然拥有不同的：

- system prompt / 协作约定
- skills / 工具使用习惯
- 目录结构理解
- 工程脚本与工作流
- 项目私有知识和执行边界

你切的不是一个“聊天机器人模式”，而是一个真实项目上下文下的 Codex agent。

### 4. 同一个人，可以拥有多种完全不同的 agent

这件事最有价值的地方，在于不同目录可以天然承接不同任务类型。

例如：

- 你可以有一个偏“个人管理”的目录，里面的 Codex 更擅长找新闻、检索资料、整理信息、沉淀日常工作流
- 你可以有一个偏“项目实现”的目录，里面的 Codex 更擅长读代码、改实现、跑测试、维护工程约定
- 你甚至可以给某个项目接入专门的外部 skills，让它只服务于这个项目特有的信息源和协作方式

因为接入面是飞书，这一点还会更实用：

- 你可以很容易在网上找到和飞书云文档、飞书协作流相关的 Codex skills
- 然后按需装进某个目录对应的 agent 环境里
- 让不同项目拥有不同的文档检索、协作集成和知识接入能力

这是一种真正可插拔的 agent 组织方式，而不是在一个统一大壳里硬塞所有能力。

### 5. 它的 runtime 是分层的

`feishu`、`runtime`、`agent_runtime`、`backends`、`storage/session` 职责分离，后续演进不会因为某个 CLI 变化而整套产品一起塌。

### 6. 它是按“长任务真的能跑”来设计的

流式回复、typing、session 串行、follow-up 合并、命令分流、本地状态持久化，都是主路径，不是补丁功能。

## 你能直接拿到什么

- Feishu 长连接接入与飞书对话内控制面
- 流式卡片回复与最终态收口
- relay session 到 backend native session 的绑定能力
- 按目录切换不同项目上下文，并复用各项目已有的 Codex 定义、skills 与习惯
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
WORKSPACE_DIR=~
WORKSPACE_DEFAULT_DIR=~/Projects
MAIN_WORKSPACE_DIR=~/Projects
DEVELOP_WORKSPACE_DIR=~/Projects

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

- 默认以飞书长连接模式工作，此时 `openrelay` 只绑定 `127.0.0.1`
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

在飞书开放平台开启长连接接收后，`openrelay` 就可以作为你本机 Codex 的远程对话入口使用。

## 命令面

### 会话与导航

- `/resume [latest|thread_id|local_session_id]`
- `/compact [thread_id|local_session_id]`，等待 compact 完成后返回
- `/status`
- `/help`

### 目录与上下文控制

- `/main [reason]`
- `/stable [reason]`
- `/develop [reason]`
- `/workspace [--page N] [--path <dir>] [--query <text>]`
- `/shortcut list|add|remove|use`

### 运行控制

- `/stop`
- `/clear`
- `/model [name|default]`
- `/sandbox [read-only|workspace-write|danger-full-access]`
- `/backend [list|name]`
- `/ping`
- `/restart`（仅管理员）

## 推荐使用方式

1. 在飞书里从一条直接任务消息开始；需要补充操作时再用 `/help`、`/resume`、`/workspace`。
2. 让 `openrelay` 把当前 scope 绑定到 backend session。
3. 同一任务就在 thread 里持续补充，而不是反复重讲背景。
4. 需要回到旧会话时，用 `/resume` 接回原生 agent thread。
5. 需要切到另一个项目上下文时，用 `/workspace` 浏览/搜索目录，或直接用快捷目录入口。

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
- 不同项目可以保留不同的 agent 定义和能力边界
- skills 可以按项目、按目录插拔，而不是被统一外壳抹平

这就是 `openrelay` 的判断。

如果你不想要一个只能 demo 的 bot，而是想要一个能在真实开发任务里活下来的远程 agent 入口，这个仓库就是为这个方向做的。

## 对外传播素材

如果你准备把这个项目发到社区、社群或社交媒体，可以直接复用这些现成材料：

- `docs/marketing/launch-kit.md`：一句话定位、受众、卖点、社区帖模板、录屏脚本
- `docs/marketing/outreach-plan.md`：三周外发节奏、渠道优先级、反馈判断标准
- `static/openrelay_social_card.svg`：仓库分享图 / 帖子封面底图
- `CHANGELOG.md`：当前公开版本的发布说明
