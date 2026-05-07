# Verification

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Verification Path
- Planned Path:
  - 用本地代码梳理流式态与最终态可能出现的过程输出类型。
  - 用 `lark-cli` 发送一张综合飞书交互式卡片，覆盖当前高亮写法、安全摘要写法和长输出折叠写法。
  - 用 `lark-cli im +messages-mget` 回读消息，记录接口可见的渲染摘要；真实客户端视觉结果仍需人工观察截图确认。
- Executed Path:
  - 已准备 `artifacts/render-sample-card.json`。
  - 已尝试 bot 身份发送，飞书返回 `230002 Bot/User can NOT be out of the chat`，说明隔离 CLI 机器人不在当前会话内。
  - 已用 user 身份发送同一张卡片，消息号 `om_x100b50f0827e4ae0c38d5ff089080b0`，发送时间 `2026-05-07 16:26:51`。
  - 已用 user 身份回读消息摘要。
- Path Notes:
  - 本次只能证明样例卡片能发出并能回读摘要；真实客户端视觉结果仍需要人工观察。
  - bot 身份发送受限，不等价于 openrelay 服务机器人真实发卡。
  - 回读摘要显示当前高亮写法不会在接口摘要里完整保留原始标签，但安全写法仍出现 `1 additionOutput preview:```diff` 粘连，说明换行分隔规则需要继续验证。

只有当实现已经完成到足以采集新证据时，才进入 `verifying`。
如果实现仍然延期到后续轮次，就不要使用 `archived`。

## Required Commands
- `jq -c . docs/task-packages/feishu-transcript-rendering-matrix/artifacts/render-sample-card.json`
- `lark-cli im +messages-send --as bot --chat-id oc_7bea2cfa55a47c1d33fb0fdc607153f2 --msg-type interactive --content "$(jq -c . docs/task-packages/feishu-transcript-rendering-matrix/artifacts/render-sample-card.json)" --idempotency-key or-022-render-sample-20260507-bot-v1`
- `lark-cli im +messages-send --as user --chat-id oc_7bea2cfa55a47c1d33fb0fdc607153f2 --msg-type interactive --content "$(jq -c . docs/task-packages/feishu-transcript-rendering-matrix/artifacts/render-sample-card.json)" --idempotency-key or-022-render-sample-20260507-user-v1`
- `lark-cli im +messages-mget --as user --message-ids om_x100b50f0827e4ae0c38d5ff089080b0 --format json`
- `uv run openharness check-tasks`

## Expected Outcomes
- 样例卡片能真实发送到飞书会话，并能让维护者比较当前高亮写法、安全摘要写法和长输出折叠写法。
- 如果 bot 身份不可用，需要明确记录限制，避免误认为已经验证服务机器人路径。
- 回读摘要和真实客户端截图应共同决定后续渲染方案，不能只依赖接口文本。

## Traceability
- `Required Outcomes` 中的真实飞书样例已获得第一条样例消息。
- 输出类型矩阵、完整渲染策略和真实客户端截图仍未完成，因此本包还不能进入实现完成或归档判断。

## Risk Acceptance
- 接受本次样例由 user 身份发送的限制，因为它仍能验证飞书客户端对交互式卡片内容的基础渲染；当需要证明 openrelay 服务机器人路径时，必须补充 bot 可见会话或真实 openrelay 回复证据。
- 接受当前只覆盖三类样例的限制，因为本轮目标是先建立方向性证据；进入设计阶段前仍需补齐完整输出类型矩阵。

## Latest Result
- 已发送真实飞书样例卡片 `om_x100b50f0827e4ae0c38d5ff089080b0`。当前证据显示换行粘连和 bot 发送权限是后续设计必须处理的两个问题。
- Latest Artifact: `docs/task-packages/feishu-transcript-rendering-matrix/artifacts/render-sample-card.json`
