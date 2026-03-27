# Verification

## Required Commands
- `.agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks`
- `uv run pytest tests/runtime/test_command_router_workspace.py -q`

## Expected Outcomes
- `/workspace select` 在当前 release workspace 内仍回显短路径。
- `/workspace select` 切到 release workspace 外的目录时，回显 workspace picker 路径而不是错误的当前项目名。
- 成功文案明确说明“下一条真实消息开始使用新 thread”。

## Latest Result
- 2026-03-19: package scaffolded from historical task notes and promoted to a formal harness package.
- 2026-03-27: `uv run pytest tests/runtime/test_command_router_workspace.py -q` 通过，覆盖：
  - 普通工作区浏览
  - thread 内禁用 `/workspace`
  - `open` / `--hidden`
  - 快捷目录切换
  - 跨 release 根目录切换后的成功文案回显
- 2026-03-27: 仓库内声明的 `.agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks` 在当前仓库不存在；本轮只能确认该路径报 `No such file or directory`，未能完成这条 harness 验证。
