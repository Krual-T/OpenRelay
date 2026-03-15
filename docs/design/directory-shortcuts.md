# Directory Shortcuts

## 目标

给飞书里的目录切换提供一条足够短、足够稳的主路径：优先通过 `/panel` 里的常用目录快捷按钮切换，再复用现有 `/cwd` 语义完成真正的 scope 目录切换。

## 为什么先做这条路径

当前系统已经把目录切换稳定收敛到 `/cwd`：

- 切目录会原地更新当前 scope 的 cwd
- 下一条真实消息才在新目录绑定新的原生 thread
- 目标目录仍然受当前 release channel 的 workspace root 约束

因此这轮不额外引入“最近目录”“新别名命令”或第二套切换状态流，而是在 `/cwd` 前面增加一层更短的入口。

## 配置来源

使用 `DIRECTORY_SHORTCUTS` 环境变量，格式为 JSON array。

每个条目包含：

- `name`：按钮展示名
- `path`：目录路径，推荐写相对路径
- `channels` / `channel`：`main`、`develop` 或 `all`

示例：

```json
[
  {"name": "docs", "path": "docs", "channels": "main"},
  {"name": "api", "path": "services/api", "channels": "develop"},
  {"name": "shared", "path": "shared", "channels": "all"}
]
```

## 作用域与解析规则

- `main`：相对 `MAIN_WORKSPACE_DIR` 解析
- `develop`：相对 `DEVELOP_WORKSPACE_DIR` 解析
- `all`：表示“同一个相对路径名在两个 channel 根目录下都可用”，不是跨 channel 复用某个绝对目录

为了让按钮点击不受“当前 cwd 已经在更深层目录里”的影响，`/panel` 里的快捷目录按钮会先把配置项解析成稳定的目标绝对路径，再复用 `/cwd <resolved-path>` 主链路。

## 命名与冲突策略

- 名称必须稳定、可扫描，避免靠上下文猜测语义。
- 如果两个快捷目录名字相同，且 channel 作用域有重叠，配置加载直接失败。
- `all` 与 `main/develop` 视为作用域重叠，不允许重名并存。

这样做的原因很直接：目录入口属于主路径，不适合保留模糊的“后者覆盖前者”隐式规则。

## 无效配置的处理

面板渲染时会过滤掉以下条目，不把坏按钮发到飞书：

- 目标路径不存在
- 目标路径不是目录
- 目标路径越出当前 channel 的 workspace root

也就是说，配置是声明式的，但真正展示给用户的入口仍然要经过当前 workspace 约束校验。

## 当前最小落地范围

- `/panel` 展示当前 channel 可用的常用目录按钮
- 点击按钮后直接触发 `/cwd` 切换
- `/help` 和 README 同步提示：如果面板里已有快捷目录，优先点按钮，而不是手写路径

这轮没有继续引入：

- 最近目录历史
- 用户态收藏编辑
- 独立的目录别名命令
