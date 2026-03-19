# OR-TASK-006 Rich-Based Feishu Command Highlighting Design

> 归档说明：该实现设计对应的 transcript 富文本高亮能力已落地；本文档仅保留为已完成实现的历史设计证据。

## Background

当前飞书 transcript card 的命令高亮已经有首轮主题映射，但命令换行仍然有一个结构性问题：

- 命令高亮和命令换行是两套逻辑，容易漂移。
- 树前缀 `│ / └` 在外层追加，实际可用宽度和高亮器内部宽度不一致。
- 超长 shell script 参数虽然已经做了语义分段，但换行仍然容易落在不理想的位置。

用户提出的新路线不是继续扩展手工包行规则，而是引入一个真正具备“样式状态”概念的渲染层，再把结果映射到飞书富文本。

## Goal

把命令高亮收敛为一条稳定链路：

1. 命令文本先变成带样式状态的中间表示。
2. 再按目标宽度包行。
3. 跨行时保留样式状态。
4. 最终映射为飞书 `<font>` 片段。

## Non-goals

- 这一轮不重写 output preview 的 pygments / diff / 语义高亮链路。
- 这一轮不追求终端 ANSI 全量兼容。
- 这一轮不把所有主题配置都抽成用户可配项，只先把实现边界收敛好。

## Decision

采用 `Rich Text spans` 作为命令高亮的中间态，而不是把原始 ANSI 字符串当主数据结构。

### Why not raw ANSI as the primary model

原始 ANSI 字符串确实可以视为“开闭状态流”，但直接在字符串上做裁剪有几个问题：

- 宽度计算必须忽略 ANSI，自然需要再建一层可见宽度模型。
- 裁剪点一旦落在 escape sequence 中间，恢复逻辑会变复杂。
- 后续还要做 HTML escape / `&nbsp;` 替换，字符串级处理容易彼此污染。

`Rich Text spans` 本质上保留了同样的样式状态，只是把状态从控制字符收敛成结构化 span，便于后续包行和飞书映射。

## Architecture

命令高亮主路径调整为：

```text
raw command
  -> shell semantic segments
  -> Rich Text spans
  -> semantic wrap(width = target_length - tree_prefix_width)
  -> Rich rendered segments
  -> Feishu <font> fragments
```

其中：

- `shell semantic segments` 负责回答“这段文本是什么角色”。
- `Rich Text spans` 负责回答“这些角色最终如何稳定映射到带颜色的渲染片段”。
- `Feishu <font>` 负责最终平台输出。

## Detailed Flow

### 1. Semantic segmentation

仍保留现有 shell-aware 扫描器，原因是：

- 纯 Bash lexer 在 `-lc "..."` 这种真实命令上粒度太粗。
- 我们还需要产品语义，例如首个 command、path、url、flag、operator 的主题角色。

因此第一步不直接依赖外部 shell highlighter 产出最终语义，而是保留当前仓库已经验证过的语义分段：

- command
- flag
- operator
- env
- url
- path
- string
- number

### 2. Rich as the style-state layer

把语义分段 append 到 `rich.text.Text`：

- 每个 segment 对应一段文本和一个 Rich style。
- 无样式 segment 直接以 plain text append。

换行仍由仓库内语义 wrapper 负责：

- 宽度使用 `target_length - 2`，显式扣除 transcript tree prefix 的两个字符宽度。
- 只在 segment 边界上换行，不在长路径这类单个 token 中间硬切。
- quoted script 参数因为在前一步已被拆成“词 + 空白”的 string segments，所以仍然可以在词边界续行。

这里之所以没有直接采用 `Text.wrap()` 作为最终包行器，是因为 Rich 的现有 overflow 策略在这个场景下有一个二选一问题：

- `fold` 会把超长路径从中间切开；
- `ignore` 会让整段 quoted script 不再按词续行。

因此最终实现是：

- 语义 wrapper 负责决定在哪里换行；
- Rich 负责把每一行的 style span 正确渲染出来。

### 3. Feishu mapping

对每一行 `Text` 调用 `render()` 得到 Rich `Segment` 序列，再逐段映射到飞书：

- 有前景色 -> `<font color='#RRGGBB'>...</font>`
- 无样式 -> 只做 HTML escape

这里不再需要把 ANSI 重新 parse 一遍。

### 4. Tree prefix ownership

树前缀仍然归 `reply_card.py` 所有：

- `│ / └` 不参与 Rich span 构造。
- 命令渲染只返回“正文行”。
- transcript 拼装时再加前缀，确保前缀永远不被染色。

## Expected Improvements

- 命令换行宽度和实际显示宽度一致。
- 同一个样式片段跨行时不需要手工维护闭合状态。
- `-lc "..."` 这类长 script 参数续行时颜色保持稳定。
- 后续如果要切主题，只需要改 semantic role -> Rich style -> Feishu color 的映射表。

## Risks

### Risk 1: 语义 wrapper 与 Rich spans 再次漂移

通过保持统一的 `ShellSegment` 事实源来控制：

- 语义角色判断只做一次；
- wrap 和 render 都基于同一组 segment。

### Risk 2: Rich style carries attributes other than foreground color

当前飞书侧只映射 foreground color。加粗、斜体、下划线暂不迁移；避免把命令 transcript 复杂化。

### Risk 3: Existing tests assume old line splits

这是预期变更。测试应验证：

- 树前缀不染色
- 样式在续行后仍保持
- 长路径不被无意义拆裂

## Validation

这一轮至少需要验证：

- `tests/test_feishu_streaming.py`
- `uv run python -m compileall src`

并补端到端样例覆盖：

- `-lc "..."` 超长 shell script
- 长路径命令
- 正文 inline code 自定义颜色不受命令链路影响
