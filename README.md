# openrelay

`openrelay` 是一个通过飞书附着到本机 agent CLI 会话的远程终端入口。

当前目标是把体验打磨成 `openrelay` 自己的一致命令心智：清晰的会话隔离、`main/develop` 工作区切换，以及 Feishu thread-first 使用方式。

同时，内部实现会保持“CLI 适配器抽象”：runtime 不关心到底是谁提供 server，只关心这个 CLI 适配器是否支持持久会话、如何发送 prompt、如何中断当前运行。

## 当前内置后端

- `codex`：通过 `codex app-server` 复用原生 session

后续如果要支持 `claude` 或其他 coding-agent CLI，只需要新增一个 backend adapter 并注册到 registry。

## 当前体验对齐点

- Feishu 支持 webhook 与 WebSocket 长连接两种接入方式
- thread-first 回复：普通回复默认优先在线程里继续
- 命令集尽量对齐：`/panel`、`/ping`、`/stop`、`/restart`、`/main`、`/stable`、`/develop`、`/new`、`/resume`、`/clear`、`/status`、`/cwd`、`/cd`、`/model`、`/sandbox`、`/tools`、`/help`
- 会话支持 `main` / `develop` 工作区切换，并写入 `data/release-events.jsonl`
- `/panel` 会发送飞书交互卡片，最近会话和常用动作都在卡片里
- `/resume` 现在会合并本地会话与可导入的原生 `~/.codex/sessions` 历史
- `FEISHU_STREAM_MODE=card` 时会显示 `openrelay` 的运行中状态卡片与 typing

## 环境变量

这版使用 `openrelay` 当前约定的配置名：

```env
PORT=3000
WEBHOOK_PATH=/feishu/webhook
DATA_DIR=./data
WORKSPACE_DIR=/absolute/path/to/your/workspace
MAIN_WORKSPACE_DIR=/absolute/path/to/main/worktree
DEVELOP_WORKSPACE_DIR=/absolute/path/to/develop/worktree

FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_CONNECTION_MODE=websocket
FEISHU_VERIFY_TOKEN=
FEISHU_BOT_OPEN_ID=ou_xxx
FEISHU_STREAM_MODE=card
FEISHU_GROUP_REPLY_ALL=false
FEISHU_GROUP_SESSION_SCOPE=sender
FEISHU_ALLOWED_OPEN_IDS=
FEISHU_ADMIN_OPEN_IDS=

MODEL_BACKEND=codex-cli
MODEL_NAME=
CODEX_CLI_PATH=codex
CODEX_MODEL_OVERRIDE=
CODEX_SANDBOX=workspace-write
CODEX_SESSIONS_DIR=~/.codex/sessions
```

说明：

- `FEISHU_VERIFY_TOKEN` 现在是可选的；如果飞书后台配置了 token，建议填上
- `WORKSPACE_DIR` 是默认工作区；`MAIN_WORKSPACE_DIR` 和 `DEVELOP_WORKSPACE_DIR` 对应 `/main` 与 `/develop`
- `MODEL_BACKEND` 当前内置只支持 `codex-cli`，但 runtime 已按 CLI 适配器抽象设计
- `FEISHU_ALLOWED_OPEN_IDS` 与 `FEISHU_ADMIN_OPEN_IDS` 是 `openrelay` 新补的权限层

## 快速开始

1. 安装依赖：

```bash
cd openrelay
uv sync --extra dev
```

2. 复制环境变量模板：

```bash
cp .env.example .env
```

3. 启动服务：

```bash
uv run openrelayd
```

4. 如果你使用 webhook 模式，在飞书开放平台把事件订阅地址指向：

```text
http://your-host:3000/feishu/webhook
```

如果你使用 `FEISHU_CONNECTION_MODE=websocket`，则无需配置 webhook 地址，但飞书后台需要开启“使用长连接接收事件/回调”。

## 命令

- `/panel` - 打开会话面板卡片
- `/ping` - 连通性检查
- `/stop` - 停止当前回复
- `/restart` - 重启当前服务进程
- `/main [reason]`、`/stable [reason]` - 切到 main 稳定工作区
- `/develop [reason]` - 切到 develop 修复工作区
- `/new [label]` - 新建隔离会话
- `/resume [list|latest|session_id]` - 恢复历史会话；若本地不存在，会自动尝试导入原生 Codex 历史
- `/clear` - 清空上下文但保留当前目录和配置
- `/status` - 查看当前会话状态
- `/cwd [path]`、`/cd [path]` - 查看或切换当前目录
- `/model [name|default]` - 查看或切换模型覆盖值
- `/sandbox [read-only|workspace-write|danger-full-access]` - 查看或切换执行模式
- `/tools`、`/help` - 查看帮助

## 当前状态

- 命令与会话体验已收敛到 `openrelay` 当前形态
- `codex app-server` 本机 smoke test 已跑通
- Feishu WebSocket、流式卡片、typing 和原生 session 导入列表已经补上；还未完全补齐的是更细的流式活动面板与外部 provider 行为差异
- 但 runtime 主流程已经按“可插拔 CLI 适配器”设计好了，后续扩展不会再把产品绑死到某一家 CLI
