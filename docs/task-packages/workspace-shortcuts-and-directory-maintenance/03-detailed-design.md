# Detailed Design

## Files Added Or Changed
- `src/openrelay/runtime/command_services/workspace_commands.py`
  - `/workspace select` 成功文案统一从这里生成。
- `tests/runtime/test_command_router_workspace.py`
  - 覆盖目录切换成功文案与跨 release 根目录的显示语义。
- `docs/task-packages/workspace-shortcuts-and-directory-maintenance/STATUS.yaml`
  - 记录本轮实现与验证证据。
- `docs/task-packages/workspace-shortcuts-and-directory-maintenance/05-verification.md`
  - 记录本轮命令级验证结果。
- `docs/task-packages/workspace-shortcuts-and-directory-maintenance/06-evidence.md`
  - 回写本轮落地证据和遗留问题。

## Interfaces
- `/workspace select <path>` 在切换目录时会清空当前 native thread，并把下一条真实消息放到新目录启动新 thread。
- 成功文案按两种路径语义展示：
  - 若目标目录仍在当前 release workspace 根下，继续使用短路径，如 `docs`。
  - 若目标目录跳出当前 release workspace 根，但仍在 workspace browser 根下，改用选择器路径，如 `~/side-project`，避免错误回显成当前 release 项目。

## Error Handling
- 不再使用“当前 scope 已原地更新”这类会误导用户认为仍复用旧 native thread 的表述。
- 当用户切到 release workspace 外的目录时，禁止继续沿用 `format_cwd()` 的 release-root 视角，否则会把目标目录错误压缩成当前项目名或绝对路径。

## Migration Notes
- 当前 package 仍有占位段落，但本轮已经把 `/workspace select` 的文案与路径显示规则落到实现和测试中。
- 后续若继续扩展最近目录或快捷目录卡片，应复用相同的路径显示规则，避免不同入口回显不一致。
