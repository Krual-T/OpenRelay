# AGENTS.md

本文件现在作为 `openrelay` 的 repository map：它负责告诉协作者“事实来源在哪里、默认工作流是什么、完成任务时需要回写什么”，而不再承担细粒度任务状态管理。

## 1. 仓库地图

### 事实来源优先级

1. `AGENTS.md`
   - 仓库地图、默认协作协议、结构约束、验证要求。
2. `.codex/skills/openharness/references/manifest.yaml`
   - harness 的机器可读入口；声明 active / archived design package 布局、状态流和 artifact 根目录。
3. `docs/designs/<task>/`
   - 设计任务的唯一事实来源；每个任务是一个独立 design package。
4. `docs/archived/designs/<task>/`
   - 已完成 design package 的归档区；保留历史事实与验证证据，但不再属于 active package 集合。
5. `docs/architecture.md`
   - 当前系统结构说明。
6. `.project-memory/`
   - 已验证的项目事实、决策和可复用 workflow。
7. `docs/archived/legacy/`
   - 历史材料归档区；仅作为 legacy evidence，不再作为当前任务事实源。

### 设计任务包协议

每个设计任务应放在 `docs/designs/<task>/`，并固定包含：

- `README.md`：任务入口页和阅读导航。
- `STATUS.yaml`：机器可读状态源。
- `01-requirements.md`：需求、目标、非目标、完成定义。
- `02-overview-design.md`：总体设计、边界、主数据流/状态流。
- `03-detailed-design.md`：详细设计、文件级落点、迁移策略。
- `04-implementation-plan.md`：执行分解、阶段顺序、提交与验证闸口。
- `05-verification.md`：验证方案与结果。
- `06-evidence.md`：落地证据、命令、剩余 follow-up。

默认阅读顺序：

1. `AGENTS.md`
2. `.codex/skills/openharness/references/manifest.yaml`
3. `docs/designs/<task>/README.md`
4. `docs/designs/<task>/STATUS.yaml`
5. `docs/designs/<task>/01-requirements.md`
6. `docs/designs/<task>/02-overview-design.md`
7. `docs/designs/<task>/03-detailed-design.md`
8. `docs/designs/<task>/04-implementation-plan.md`
9. `docs/designs/<task>/05-verification.md`
10. `docs/designs/<task>/06-evidence.md`

## 2. 默认工作流

### 进入仓库后

- 先读 `AGENTS.md`，建立仓库地图。
- 先把 `openharness` 视为本仓库的默认入口技能；任何可能涉及仓库协议、design package、验证流或技能路由的工作，都先从它开始判断该走哪个 skill。
- 再读 `.codex/skills/openharness/references/manifest.yaml`，确认 harness 协议。
- 运行 `uv run python .codex/skills/openharness/scripts/openharness.py bootstrap` 查看当前 active design packages。
- 只在 design package 足够清晰时开始实现；若任务边界缺失，先补设计包而不是直接改代码。

### 执行任务时

- 先经过 `openharness` 做 skill routing，再进入 `brainstorming`、`systematic-debugging`、`writing-plans` 或直接实现；
- 需求、总体设计、详细设计分层书写，不要混在一个随手增长的长文档里。
- 改动前先确定主路径、状态流和验证方式。
- 复杂改动先整理结构，再实现局部。
- 若发现稳定可复用事实，应优先回写 `.project-memory/`。

### 完成任务时

- 先更新 `05-verification.md` 和 `06-evidence.md`；若本轮需要显式执行拆解，再更新 `04-implementation-plan.md`。
- 再更新 `STATUS.yaml` 中的 `status`、`updated_at`、证据字段。
- 当 design package 已完成并不再属于 active work 时，应将 `STATUS.yaml.status` 设为 `archived`，并把整个包从 `docs/designs/<task>/` 移动到 `docs/archived/designs/<task>/`。
- 归档后必须同步修正该 package 内部引用，以及仓库内指向该 package 的证据或 memory 引用。
- 每次完成一轮可独立成立的改动后，应做一次聚焦提交。

## 3. 工程风格

### 思维方式

- 先理解整体，再改局部；先建立模型，再写实现。
- 优先解决根因，而不是给症状打补丁。
- 重视长期稳定性、可维护性和演化能力。
- 表达应直接、明确、克制，不堆术语，不做表面包装。

### 代码风格偏好

- 偏好语义明确、层次分明、边界清楚的实现。
- 抽象必须服务于降低复杂度；如果抽象增加理解成本，就不该存在。
- 不喜欢冗余代码、重复状态、重复包装、补丁式分支叠加。
- 命名应直接表达真实语义，避免模糊缩写。
- 模块依赖尽量单向、稳定，避免循环依赖和隐式耦合。
- 错误处理要明确，不要吞错，不要让失败路径不可见。

### 结构洁癖

- 主路径应尽量短、直、稳定，不应被边角兼容逻辑淹没。
- 相近逻辑应被收敛，而不是复制出多个相似版本。
- 同一层级代码保持相近抽象粒度，不要忽粗忽细。
- 能通过重组结构解决的问题，不要优先靠注释、标志位或特判堆起来。

## 4. 文档与验证协议

- 影响使用方式、配置方式、架构分层的改动，应同步更新对应 design package。
- 需求变化先写 `01-requirements.md`；总体设计变化写 `02-overview-design.md`；实现落点变化写 `03-detailed-design.md`；需要阶段化执行方案时写 `04-implementation-plan.md`。
- 完成前至少运行：
  - `uv run python .codex/skills/openharness/scripts/openharness.py check-designs`
  - 当前 design package 在 `STATUS.yaml.verification.required_commands` 中声明的命令
- 若本轮只是补设计，仍应保证 design package 协议完整。

## 5. Python / uv 约定

- 仓库内 Python 相关命令统一使用 `uv run ...`。
- 工作流脚本依赖应写入 `pyproject.toml`，不要依赖会话里的临时安装。
- 只有明确的一次性临时场景才使用 `uv run --with ...`。

## 6. 提交要求

- 每次完成一轮可独立成立的改动后，都应进行一次 `git commit`。
- 提交粒度尽量聚焦；一个提交只解决一个明确问题。
- 提交信息应准确描述“为什么改”以及“改了什么”。
- 如果改动尚未通过最基本的自检，不应急于提交。

如果用户当前任务与上述约定冲突，以用户明确要求为准。
