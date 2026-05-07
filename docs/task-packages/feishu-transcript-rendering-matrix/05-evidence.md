# Evidence

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Residual Risks
- 真实客户端截图或人工观察尚未写入。
- 机器人身份验证尚未完成；隔离 CLI 机器人当前不在目标会话内。
- 输出类型矩阵尚未覆盖全部 live turn item。

## Manual Steps
- 在飞书客户端打开消息 `om_x100b50f0827e4ae0c38d5ff089080b0`，观察 A、B、C 三个面板：
  - A 面板是否暴露 `<font>`、`<text_tag>`、`&nbsp;`、`<br>` 原始标记。
  - B 面板的 `Diff summary`、`Output preview` 和代码块是否粘连。
  - C 面板默认折叠是否明显降低过程日志干扰。
- 2026-05-07 用真实 CardKit streaming 更新链路发送去掉 `=====output=====` 后的长输出样本，回读确认 `has_output_marker: false`。

## Files
- `docs/task-packages/feishu-transcript-rendering-matrix/README.md`
- `docs/task-packages/feishu-transcript-rendering-matrix/STATUS.yaml`
- `docs/task-packages/feishu-transcript-rendering-matrix/01-requirements.md`
- `docs/task-packages/feishu-transcript-rendering-matrix/04-verification.md`
- `docs/task-packages/feishu-transcript-rendering-matrix/05-evidence.md`
- `docs/task-packages/feishu-transcript-rendering-matrix/artifacts/render-sample-card.json`

## Commands
- `uv run openharness new-task feishu-transcript-rendering-matrix --auto-id --title "Feishu Transcript Rendering Matrix" --summary "梳理流式输出和 Execution Log 的内容类型、排版规则与真实飞书卡片验证矩阵。"`
- `jq -c . docs/task-packages/feishu-transcript-rendering-matrix/artifacts/render-sample-card.json`
- `lark-cli im +messages-send --as bot --chat-id oc_7bea2cfa55a47c1d33fb0fdc607153f2 --msg-type interactive --content "$(jq -c . docs/task-packages/feishu-transcript-rendering-matrix/artifacts/render-sample-card.json)" --idempotency-key or-022-render-sample-20260507-bot-v1`
- `lark-cli im +messages-send --as user --chat-id oc_7bea2cfa55a47c1d33fb0fdc607153f2 --msg-type interactive --content "$(jq -c . docs/task-packages/feishu-transcript-rendering-matrix/artifacts/render-sample-card.json)" --idempotency-key or-022-render-sample-20260507-user-v1`
- `lark-cli im +messages-mget --as user --message-ids om_x100b50f0827e4ae0c38d5ff089080b0 --format json`
- `uv run openharness transition feishu-transcript-rendering-matrix requirements_ready`
- `lark-cli api POST /open-apis/cardkit/v1/cards --as bot --data ...` + `lark-cli api POST /open-apis/im/v1/messages --as bot --params '{"receive_id_type":"chat_id"}' --data ...` + `lark-cli api PUT /open-apis/cardkit/v1/cards/7637128147863342285/elements/streaming_content/content --as bot --data ...`
- `lark-cli im +messages-mget --as bot --message-ids om_x100b50fc37b07080c4a4d84e78d6221 -q '{...has_output_marker...}'`，结果 `has_output_marker: false`。

## Artifact Paths
- `docs/task-packages/feishu-transcript-rendering-matrix/artifacts/render-sample-card.json`
- 飞书消息：`om_x100b50f0827e4ae0c38d5ff089080b0`
- 去掉 `=====output=====` 后的真实长输出 CardKit 样本：card `7637128147863342285`，message `om_x100b50fc37b07080c4a4d84e78d6221`。

## Follow-ups
- 补齐输出类型矩阵：command、web_search、reasoning、commentary、file_change、plan、collab、backend_event、summary、最终答案、运行中 spinner、错误输出、diff 输出、长输出。
- 对流式态和最终态分别提出渲染策略，不再无条件复用同一套 `<font>` 高亮输出。
- 找到可用 bot 验证会话，补充机器人身份真实发卡证据。
