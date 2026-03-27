# Evidence

## Files
- `src/openrelay/runtime/command_services/workspace_commands.py`
- `tests/runtime/test_command_router_workspace.py`
- `docs/task-packages/workspace-shortcuts-and-directory-maintenance/STATUS.yaml`
- `docs/task-packages/workspace-shortcuts-and-directory-maintenance/03-detailed-design.md`
- `docs/task-packages/workspace-shortcuts-and-directory-maintenance/05-verification.md`
- `docs/task-packages/workspace-shortcuts-and-directory-maintenance/06-evidence.md`

## Commands
- `.agents/skills/openharness/using-openharness/scripts/openharness.py new-design workspace-shortcuts-and-directory-maintenance OR-013 "Workspace Shortcuts And Directory Maintenance" --owner codex --summary "Reduce repeated workspace navigation with high-frequency shortcuts and maintenance flows."`
- `uv run pytest tests/runtime/test_command_router_workspace.py -q`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks`

## Observed Evidence
- `/workspace select` 成功文案现在区分两种显示路径：
  - release workspace 内继续显示短路径，如 `docs`
  - release workspace 外改显示 workspace picker 路径，如 `~/side-project`
- 成功文案删除了“当前 scope 已原地更新”，改为明确提示“当前 scope 会从下一条真实消息开始使用新 thread”。
- 新增回归测试覆盖跨 release 根目录切换，防止再次把外部目录错误回显成当前项目。

## Follow-ups
- 修正 `STATUS.yaml.verification.required_commands` 中失效的仓库内 `openharness.py` 路径，避免后续 package 验证继续被假失败阻塞。
- 继续补全本 package 的实现级详细设计，覆盖最近目录、快捷目录卡片入口和维护路径。
