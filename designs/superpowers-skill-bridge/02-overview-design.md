# Overview Design

## System Boundary
本设计只处理“把外部已安装 superpowers 显式带进仓库”这件事，不处理 superpowers 的安装器、版本管理或内容同步。

## Proposed Structure
- `.codex/skills/<skill-name>`
  - 每个条目都是一个软链接，指向 `/home/Shaokun.Tang/.codex/superpowers/skills/<skill-name>`。
- `AGENTS.md`
  - 说明仓库采用 soft-link 模型接入 superpowers。
- `tests/harness/test_design_harness.py`
  - 对关键 symlink 和安装根目录做最小回归保护。

## Key Flows
1. 协作者进入仓库后先读 `AGENTS.md`。
2. 在 `.codex/skills/` 下直接看到 soft-linked superpowers skills。
3. 继续以 `designs/<task>/` 作为任务事实源，以 soft-linked skills 作为 workflow 库。

## Trade-offs
- soft-link 比桥接说明更直接，但依赖当前机器上的绝对路径。
- 不复制原始 skill 内容，避免仓库里再维护一份会漂移的副本。
