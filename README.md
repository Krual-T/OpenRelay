# openrelay

`openrelay` 是一个通过飞书附着到本机 agent CLI 会话的远程终端入口。

当前目标是把体验打磨成 `openrelay` 自己的一致命令心智：清晰的会话隔离、`main/develop` 工作区切换，以及 Feishu thread-first 使用方式。

同时，内部实现会保持“CLI 适配器抽象”：runtime 不关心到底是谁提供 server，只关心这个 CLI 适配器是否支持持久会话、如何发送 prompt、如何中断当前运行。

飞书侧现在统一走官方 Python SDK `lark-oapi`，包括消息发送、事件订阅和长连接接入。

## 当前内置后端

- `codex`：通过 `codex app-server` 复用原生 session

后续如果要支持 `claude` 或其他 coding-agent CLI，只需要新增一个 backend adapter 并注册到 registry。

## 当前体验对齐点

- Feishu 支持 webhook 与 WebSocket 长连接两种接入方式
- thread-first 回复：普通回复默认优先在线程里继续
- 命令集尽量对齐：`/panel`、`/ping`、`/stop`、`/restart`、`/main`、`/stable`、`/develop`、`/new`、`/resume`、`/clear`、`/status`、`/cwd`、`/cd`、`/shortcut`、`/model`、`/sandbox`、`/tools`、`/help`
- 会话支持 `main` / `develop` 工作区切换，并写入 `data/release-events.jsonl`
- `/panel` 现在是飞书里的总入口：总览页下再分 `sessions / directories / commands / status` 四类结果面
- `/panel`、`/resume list`、`/help` 这类导航型卡片在按钮切换时会优先原地更新，避免翻页和层级切换不断刷新消息
- `/panel` 的会话结果继续复用 `/resume` 主路径，目录结果继续复用 `/cwd` 主路径，避免再长出第二套执行语义
- `/panel` 仍会按 `main / develop` 作用域显示常用目录快捷按钮，点击后直接复用 `/cwd` 切换
- `/resume` 现在只恢复本地 backend session；thread 只作为会话绑定，不再直接暴露成恢复目标
- `FEISHU_STREAM_MODE=card` 时会显示 `openrelay` 的运行中状态卡片与 typing
- 主回复卡片、运行中卡片和常驻操作卡片已收敛到一套更接近 Codex CLI 的低噪音主题语义；`card` 模式下会在同一张 CardKit 卡里收口最终回复并折叠 reasoning
- 当前回复还没结束时，继续发消息会自动排到下一轮；连续补充会合并成一轮 follow-up
- `/ping`、`/status`、`/usage`、`/help`、`/panel` 这类诊断命令在当前回复尚未结束时也会立即返回，不再被同 session 串行锁静默卡住
- 串行粒度现在按本地 backend `session_id` 收敛：同一个 session 的多 thread 串行，不同 session 可以并发
- 飞书图片消息会先通过消息资源接口下载到本地临时文件，再作为图像 input 传给 `codex app-server`

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
FEISHU_ENCRYPT_KEY=
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
CODEX_SQLITE_HOME=
CODEX_REQUEST_TIMEOUT_SECONDS=
DIRECTORY_SHORTCUTS=[{"name":"docs","path":"docs","channels":"main"},{"name":"api","path":"services/api","channels":"develop"}]
```

说明：

- `FEISHU_VERIFY_TOKEN` 现在是可选的；如果飞书后台配置了 token，建议填上
- `FEISHU_ENCRYPT_KEY` 用于飞书事件加密；只有你在开放平台开启了加密推送时才需要配置
- `WORKSPACE_DIR` 是默认工作区；`MAIN_WORKSPACE_DIR` 和 `DEVELOP_WORKSPACE_DIR` 对应 `/main` 与 `/develop`
- `MODEL_BACKEND` 当前内置只支持 `codex-cli`，但 runtime 已按 CLI 适配器抽象设计
- `CODEX_SQLITE_HOME` 默认会落到 `DATA_DIR/codex-sqlite`，把 `codex app-server` 的 SQLite state / log 与你交互式 `~/.codex` 隔离，避免共享同一份不断增长的 state 库
- `CODEX_REQUEST_TIMEOUT_SECONDS` 默认留空，表示不对 `codex app-server` 请求施加固定超时；如需显式限制，可填正数秒
- `FEISHU_ALLOWED_OPEN_IDS` 与 `FEISHU_ADMIN_OPEN_IDS` 是 `openrelay` 新补的权限层
- `DIRECTORY_SHORTCUTS` 用 JSON array 描述 `/panel` 常用目录快捷入口；`channels` 支持 `main` / `develop` / `all`
- 快捷目录按钮内部会先解析成稳定目标路径，再复用 `/cwd <path>` 主路径，避免受当前 cwd 深度影响

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

如果你本机按仓库当前约定安装成 systemd service，默认使用的是用户级 unit，而不是系统级 unit：

```bash
XDG_RUNTIME_DIR=/run/user/$(id -u) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus \
  systemctl --user status openrelay.service

XDG_RUNTIME_DIR=/run/user/$(id -u) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus \
  systemctl --user restart openrelay.service
```

- unit 文件路径：`~/.config/systemd/user/openrelay.service`
- 不要直接用系统级 `systemctl status openrelay.service` 判断服务是否存在；那会把用户级 unit 误判成“没有这个服务”
- 当前用户级 unit 的 `ExecStart` 约定是 `uv run openrelayd`

4. 如果你使用 webhook 模式，在飞书开放平台把事件订阅地址指向：

```text
http://your-host:3000/feishu/webhook
```

如果你使用 `FEISHU_CONNECTION_MODE=websocket`，则无需配置 webhook 地址，但飞书后台需要开启“使用长连接接收事件/回调”。

## 命令

- `/panel [sessions|directories|commands|status]` - 打开总入口或直接进入对应结果面；`sessions` 额外支持 `--page` 与 `--sort`，卡片按钮切换时优先留在同一张卡
- `/ping` - 连通性检查
- `/stop` - 停止当前回复
- `/restart` - 重启当前服务进程
- `/main [reason]`、`/stable [reason]` - 切到 main 稳定工作区
- `/develop [reason]` - 切到 develop 修复工作区
- `/new [label]` - 新建隔离会话
- `/resume [list|latest|session_id]` - 恢复本地 backend session；不再直接导入或暴露原生 Codex thread 历史
- `/clear` - 清空上下文但保留当前目录和配置
- `/status` - 查看当前会话状态
- `/cwd [path]`、`/cd [path]` - 查看或切换当前目录
- `/shortcut list|add|remove|cd` - 在飞书里维护常用目录快捷入口，并复用 `/cwd` 快速切换
- `/model [name|default]` - 查看或切换模型覆盖值
- `/sandbox [read-only|workspace-write|danger-full-access]` - 查看或切换执行模式
- `/tools`、`/help` - 查看当前会话阶段、优先操作建议、常用流程和命令速查

推荐路径是：先 `/panel`，再点进 `sessions / directories / commands / status` 对应结果面；其中会话结果负责“找回哪条会话”，目录结果负责“进哪个目录”，命令结果负责“高频动作直达”，状态结果负责“先判断现场”。这些按钮导航、翻页和返回总览会优先停留在同一张卡内完成。

如果你的 `/panel` 已配置常用目录快捷按钮，优先直接点按钮切目录；没有合适入口时再手写 `/cwd <path>`。

## 当前状态

- 命令与会话体验已收敛到 `openrelay` 当前形态
- `codex app-server` 本机 smoke test 已跑通
- Feishu WebSocket、流式卡片和 typing 已经补上；还未完全补齐的是更细的流式活动面板与外部 provider 行为差异
- 但 runtime 主流程已经按“可插拔 CLI 适配器”设计好了，后续扩展不会再把产品绑死到某一家 CLI

## 连续消息的默认心智

- 同一任务继续时，通常不用先发命令，直接补充消息即可。
- 如果上一条回复还在生成，新的普通文本会进入下一轮 follow-up；连续补充会自动合并。
- 如果你想立刻打断当前回复，发送 `/stop`；已确认收到的补充消息会在停止后继续处理。
- 如果你其实已经切到新任务，不要继续堆在同一会话里，直接 `/new <label>`。
- 飞书侧这版不依赖“编辑上一条消息”来驱动 runtime；想修正内容时，直接补发一条，或 `/stop` 后重发。
