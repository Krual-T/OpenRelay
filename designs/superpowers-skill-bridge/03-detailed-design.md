# Detailed Design

## Files Added Or Changed
- `.codex/skills/<skill-name>`
  - 为每个已安装 superpowers skill 建立软链接。
- `tests/harness/test_design_harness.py`
  - 增加对关键 symlink 存在性和目标根目录的校验。

## Interfaces
- Skill entrypoint:
  - `.codex/skills/using-superpowers`
  - `.codex/skills/using-git-worktrees`
  - `.codex/skills/writing-plans`
  - `.codex/skills/executing-plans`
  - `.codex/skills/verification-before-completion`
  - 以及其它 soft-linked superpowers skills

## Error Handling
- 软链接断裂时，测试会优先暴露问题。
- 若安装根目录变化，应重建 symlink，而不是在仓库里复制技能内容。

## Migration Notes
- 本轮移除了仓库内额外的 bridge 配置层，直接采用 symlink-first。
- 未来若要跨机器共享，可再补一个小脚本做 symlink refresh，但当前先保持最短主路径。
