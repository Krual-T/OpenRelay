# Feishu Card Theme

## 目标

让飞书里的主回复卡片、运行中卡片和常驻操作卡片共享同一套低噪音主题约定，尽量继承 Codex CLI 的层级感和可扫描性，而不是继续在各处零散拼接样式。

## 主题层级

### 1. 外壳层

- 静态卡片统一复用 `src/openrelay/card_theme.py` 提供的 card shell。
- 统一收敛 `wide_screen_mode / enable_forward / update_multi`。
- header template 只承担状态语义，不承载过多信息密度。
- 如果客户端对 header template 着色不明显，优先依赖正文里的 hero / markdown panel，而不是继续把可读性押在 header 上。

### 2. 内容层

- 标题保持短、直接、可扫描。
- 命令、路径、会话 ID 等继续使用反引号，保留 CLI 的 monospace 心智。
- 状态提示不依赖大段解释，而是靠稳定 badge + 标题语义表达当前阶段。
- 需要更强层次时，优先用 markdown panel（例如代码块底板）承载状态元信息，而不是继续堆叠 blockquote。

### 3. 运行中层

- 运行中卡片继续收敛为 `header / details / body` 三段。
- `header` 负责当前阶段和状态 badge。
- `details` 负责当前动作、最近结果、耗时。
- `body` 只承载流式正文，不混入过多控制信息。

## 状态语义

当前最小主题语义如下：

- `running`：蓝色外壳 / 进行中 badge
- `success`：绿色外壳 / 已完成 badge
- `error`：红色外壳 / 失败 badge
- `cancelled`：灰色外壳 / 已取消 badge
- `info`：蓝色外壳 / 信息 badge

运行中 CardKit 卡片受平台能力限制，不额外模拟终端式大面积颜色，而是保留状态 badge、emoji、markdown panel 和结构层级；最终态和静态卡片也不再把颜色反馈完全押在 header template 上。

## 组件映射

- 主回复卡片：`src/openrelay/runtime_live.py` 的 `build_reply_card()` 走统一 shell，并根据最终文案推断成功 / 失败 / 取消语义。
- 运行中卡片：`src/openrelay/render.py` 负责把 live state 映射到统一主题文本；`src/openrelay/streaming_card.py` 负责把它落到 CardKit 结构，并在 final sections 中补上最终状态 badge。
- 常驻操作卡片：`/help`、`/panel`、`/resume list` 统一复用同一 shell，避免继续复制 header/config 约定。

## 保留与舍弃

### 保留

- 短标题 + 清晰层级
- 命令 / 路径 / ID 的 monospace 表达
- 状态语义的稳定 badge
- 轻量 emoji / spinner 作为运行中提示

### 主动舍弃

- 终端 ANSI 颜色和整套 terminal chrome
- 为了“像终端”而堆叠的大量日志噪音
- 在飞书卡片里强行复制 diff/终端布局细节
- 依赖局部特判维持样式一致性

## 当前收敛范围

这一轮先收敛两条主路径：

- 一个主回复卡片：`build_reply_card()`
- 一个运行中卡片：`render_live_status_sections()` + `build_final_sections()`

`/panel`、`/help`、`/resume list` 同步复用统一 shell，但没有试图在这一轮就把所有卡片都做成完全一致的布局模板。
