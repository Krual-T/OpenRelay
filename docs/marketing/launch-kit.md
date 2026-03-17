# OpenRelay Launch Kit

更新时间：2026-03-18

这份文档不是泛泛的“宣传建议”，而是 `openrelay` 当前可以直接拿去对外发的内容包。

## 1. 一句话定位

`openrelay` 把你本机已经调好的 coding agent，以真实 session、真实目录上下文、真实流式执行的方式接进飞书。

## 2. 面向谁

最适合这三类人：

- 已经在本机重度使用 `Codex`，不想换成另一个把工作流重做一遍的平台。
- 团队日常沟通在飞书里，希望把 coding agent 接进现有 thread，而不是额外开一个 Web 壳层。
- 需要按项目、按目录切不同 agent 定义，希望保留本地 skills、提示词、脚本和项目约定的人。

不适合的人也很明确：

- 只想要一个开箱即用的通用聊天 bot，而不关心 session 真实性。
- 不在飞书里协作，也不需要 IM 里的 thread-first 工作流。
- 还没形成自己的本地 agent 工作方式，暂时不会从目录级 agent 组织里获益。

## 3. 核心卖点

对外只反复讲下面四个点，不要分散：

1. **真实 session**：`/resume` 续的是 backend 原生会话，不是重喂历史消息。
2. **真实项目上下文**：你切换的是本机目录和对应 agent 约定，不是切一个 bot 模式。
3. **thread-first 协作**：同一个飞书 thread 内持续追问、补充、停止、继续，不需要反复重讲背景。
4. **backend-neutral runtime**：主路径现在是 `Codex app-server`，但整体 runtime 没绑死单一 provider。

## 4. 电梯稿

### 10 秒版

把本机 `Codex` 接进飞书，而且保留真实 session 和真实项目上下文，不是套壳问答 bot。

### 30 秒版

`openrelay` 是一个把飞书变成 coding agent 远程控制面的服务。它不是把聊天记录重新塞给模型，而是把 backend 原生 session、目录级项目上下文、流式执行状态和 thread 内 follow-up 稳定连起来。对已经把本机 `Codex` 调顺的人来说，价值在于：你不需要换平台，只是把现有 agent 工作方式接进飞书。

### 适合 README / 社区简介的长版

`openrelay` 把飞书变成一个真正可用的 coding agent 远程控制面，而不是演示味很重的“问答机器人”。它保留 backend 原生 session，允许按目录切不同项目上下文，把运行中的流式执行过程和最终结果稳定投影回飞书 thread。你复用的是本机已经调好的 `Codex` 工作流、skills、提示词和项目约定，而不是迁移到另一个重新定义 agent 的平台。

## 5. 对外发文模板

### GitHub 仓库简介

把你的 coding agent 接进飞书：真实 session、thread-first follow-up、目录级项目上下文、可插拔 backend runtime。

### X / Twitter

I built `openrelay`: a way to plug your local coding agent into Feishu without flattening it into a chatbot shell.

What matters:
- real backend sessions, not replayed chat history
- thread-first follow-ups inside Feishu
- per-directory agent context from your local workspace
- streaming execution projected back into chat

If you already use Codex locally and want a real remote control surface, this is for you.

Repo: https://github.com/Krual-T/OpenRelay

### 中文朋友圈 / 即刻 / 飞书群

我把一个自己更想用的方向做出来了：不是再做一个“聊天套代码”的 bot，而是把本机已经调好的 coding agent，以真实 session 的方式接进飞书。

`openrelay` 现在能做的核心事情：
- `/resume` 接回 backend 原生会话，不是重喂上下文
- 在同一个飞书 thread 里连续追问、补充、停止、继续
- 按目录切不同项目上下文，保留各项目自己的 Codex 约定和 skills
- 把流式执行状态稳定投影回聊天界面

如果你本来就在本机重度用 Codex，又希望把它接进飞书作为远程工作台，可以看看：
https://github.com/Krual-T/OpenRelay

### Hacker News

Title:
`OpenRelay: connect your local Codex session to Feishu threads`

Body:
Built this because most “chat with code” tools break down once the task stops being a demo.

`openrelay` takes a different route: Feishu is only the control surface, while the backend session stays real. That means session resume is native, follow-ups happen inside the same thread, project context comes from the actual workspace directory, and streaming execution is projected back into chat.

Current main path is `codex app-server`; the runtime shape is backend-neutral so it can host more adapters over time.

If you already have a local Codex workflow and want to keep your own prompts, skills, directory conventions, and project boundaries instead of moving into another agent shell, that is the use case.

Repo: https://github.com/Krual-T/OpenRelay

### Reddit / r/LocalLLaMA / r/ChatGPTCoding 风格

I wanted Feishu to work like a remote control surface for my local coding agent, not like another wrapper that redefines the workflow.

So I built `openrelay`:
- native session resume instead of replaying history
- thread-first follow-ups in Feishu
- per-directory project context from the actual local workspace
- streaming execution + final state projected back into chat

It currently uses `codex app-server` as the main backend path.

Repo: https://github.com/Krual-T/OpenRelay

Curious whether others also want IM-native agent control instead of a separate web shell.

### V2EX / 掘金标题候选

- 我做了个把本机 Codex 真正接进飞书的项目：OpenRelay
- 不是聊天套壳：一个以真实 session 为中心的飞书 coding agent 入口
- 把你本机调好的 Codex 接进飞书，而不是迁移到另一个 agent 平台

## 6. Demo 录屏脚本

推荐控制在 90 秒内，顺序不要变：

1. 飞书里发一条真实开发任务。
2. 展示流式回复正在生成。
3. 在线程里补一句 follow-up，让它继续处理而不是重开上下文。
4. 执行一次 `/resume latest`，证明接的是原生 session。
5. 切到另一个目录或快捷目录，证明 agent 上下文真的变了。
6. 回到 README，落一句话：Feishu 只是控制面，backend session 必须是真的。

## 7. 渠道优先级

第一波只打下面四类，不要同时铺太开：

1. **GitHub README + 仓库描述**：这是所有外链的落点。
2. **中文开发者社区**：V2EX、掘金、飞书相关社群，更容易理解“飞书 + 本机 Codex”这个场景。
3. **英文技术社区**：X、Hacker News、Reddit，用来验证“thread-first remote agent control”是否有跨地区需求。
4. **熟人定向转发**：发给已经重度用 `Codex` 或长期在飞书里协作的人，收第一批真实反馈。

## 8. FAQ 口径

### 它和各种聊天壳 / agent 平台有什么区别？

核心区别不是“也能聊天”，而是 `openrelay` 不试图替你重新定义 agent。它保留的是你本机已经存在的 session、目录结构、技能和项目约定。

### 为什么强调真实 session？

因为很多工具的“连续对话”本质上只是重发历史文本。一旦任务长、追问多、项目上下文复杂，这种连续性很容易失真。

### 为什么是飞书？

因为很多团队真实沟通就在飞书 thread 里，远程控制面放在已有协作现场，比再开一个独立壳层更自然。

## 9. 发布前检查

- README 首屏就能让人理解“它是什么，不是什么”。
- 仓库里至少有一张社交分享图或录屏封面。
- 对外帖子的链接统一落到 GitHub 仓库主页。
- 首帖只讲一个判断：`real session + real workspace context in Feishu`。
- 录屏或截图尽量证明 thread follow-up 与 `/resume`，不要只截静态卡片。
