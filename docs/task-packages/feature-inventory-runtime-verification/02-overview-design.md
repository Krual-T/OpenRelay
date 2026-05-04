# Overview Design

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## System Boundary
本包覆盖“功能事实”和“验证事实”的组织方式，不直接实现业务功能。

覆盖范围：

- 用户可见入口：文本命令、普通消息、卡片按钮、卡片表单、流式卡片、最终回复。
- 实际作用：runtime 命令路由、session 状态变化、workspace 切换、backend turn、stop/interrupt、reply 发送。
- 可观测证据：`openrelay-trace`、SQLite message trace、状态库、飞书 SDK/官方工具可见事件、必要时的手动观察。
- 调研边界：飞书官方 CLI 或官方调试工具是否能作为真实 UI / 消息 / 卡片流式观测面。

不覆盖范围：

- 不把所有飞书 UI 像素级表现自动化。
- 不立即重构 observability 或 Log Manager。
- 不立即替换已有测试结构。

## Proposed Structure
推荐把产出组织成三层。

1. **Feature Inventory**
   - 记录用户入口、展示面、命令文本或卡片 action、功能说明。
   - 示例字段：`feature_id`、`ui_surface`、`trigger`、`expected_user_feedback`。
2. **Runtime Effect Map**
   - 记录实际副作用和状态变化。
   - 示例字段：`session_effect`、`backend_effect`、`storage_effect`、`reply_effect`。
3. **Verification Matrix**
   - 记录验证方式和证据来源。
   - 示例字段：`pytest_coverage`、`local_replay`、`real_feishu_steps`、`trace_query`、`official_tool_observation`、`known_blind_spots`。

这三层可以先落成 Markdown 表格；如果后续需要机器读取，再迁移为 YAML 或 JSON。

## Key Flows
主验证流如下：

1. 维护者从功能清单选择一个功能，例如 `/workspace`。
2. 清单给出用户应执行的飞书操作，以及预期 UI 反馈。
3. 验证矩阵给出本地证据查询方式，例如按 incoming message id 或最近 trace 查询。
4. 用户在飞书触发操作。
5. 维护者用 `openrelay-trace` 或更高层验证 CLI 查询实际链路。
6. 对照矩阵判断：
   - UI 是否符合预期。
   - runtime 是否执行正确分支。
   - session / backend / reply 是否发生预期副作用。
   - 是否存在官方工具或 trace 看不到的盲区。

飞书官方 CLI 调研流如下：

1. 查官方资料，确认是否存在可安装、可脚本化、可查询消息或事件的 CLI / 调试工具。
2. 验证它是否能覆盖 openrelay 关心的对象：消息事件、卡片 action、卡片 update、流式更新、最终回复。
3. 如果能覆盖，记录最小命令和证据格式。
4. 如果不能覆盖，记录缺口，并把本地 trace + 手动观察作为主路径。

## Stage Gates
- 明确第一版清单字段和矩阵字段。
- 明确飞书官方工具调研的问题清单。
- 明确真实飞书手动触发与本地 trace 判断的主路径。
- 明确降级方向：如果官方工具无法观测 UI，则不能把 UI 自动观测作为完成条件，只能使用手动观察 + 本地 trace。

## Trade-offs
推荐方案：先做文档化清单和矩阵，再决定是否工具化。

收益：

- 成本低，能快速暴露功能覆盖缺口。
- 不依赖飞书官方 CLI 立即可用。
- 能直接复用已有 `openrelay-trace` 和测试资产。

代价：

- 初期仍需要人工触发真实飞书用例。
- Markdown 表格不如结构化文件容易自动校验。

备选方案：直接实现一个完整真实运行验证 CLI。

- 优点是一步到位，后续自动化程度更高。
- 问题是当前功能边界和官方工具能力都没确认，直接实现容易把错误假设固化进工具。

因此本包先推荐“清单和矩阵优先”，把工具实现放到详细设计之后。

## Overview Reflection
已接受的挑战：仅靠 `pytest` 不能证明真实飞书 UI 正常，因此矩阵必须包含真实运行证据。

已拒绝的挑战：把飞书官方 CLI 预设成主验证路径。拒绝原因是当前还没有官方证据证明它能观测 openrelay 关心的卡片流式 UI 细节。

已延期的挑战：是否把功能清单做成机器可读格式。延期到详细设计阶段，触发条件是矩阵字段稳定且需要自动化校验。
