# Verification

## Required Commands
- `openharness check-tasks`
- `uv run pytest tests/runtime/test_command_router_workspace.py -q`
- `uv run pytest tests/runtime/test_command_router_admin.py tests/runtime/test_help_renderer.py tests/runtime/test_reply_policy.py tests/runtime/test_panel_service.py tests/runtime/test_command_router_workspace.py -q`

## Expected Outcomes
- `/main`、`/stable`、`/develop` 不再作为用户命令主路径存在。
- `/help`、`/status`、面板、会话列表不再展示 release channel。
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
- 2026-03-27: `uv run pytest tests/runtime/test_command_router_admin.py tests/runtime/test_help_renderer.py tests/runtime/test_reply_policy.py tests/runtime/test_panel_service.py tests/runtime/test_command_router_workspace.py -q` 通过，覆盖：
  - `/develop` 不再作为已实现命令存在
  - 帮助文本不再列出 `/main`、`/develop`
  - `/status` 不再输出 `channel=`
  - 面板与工作区相关现有回归仍通过
- 2026-03-27: `openharness check-tasks` 通过；此前失效的仓库内 `openharness.py` 路径已从当前 active package 约定中移除。
