# Evidence

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Residual Risks
- 真实飞书后续回复验证尚未在本包内完成；当前状态只能支撑 `detailed_ready`。
- 同一个 backend `native_session_id` 被多个本地会话同时运行时，是否需要 native-session 级串行化仍是实施阶段风险。
- 恢复入口关闭、归档、清理、数量上限和复用提示已延期，长期入口治理仍需后续任务承接。

## Manual Steps
- 本轮未执行真实飞书人工点击验证。
- 后续真实验证建议：发送 `/resume`，连续点击两条不同后端会话，分别回复两条成功消息，再用 trace 或 SQLite 查询对应关系。

## Files
- `docs/task-packages/resume-binding-lifecycle/README.md`：更新任务状态说明。
- `docs/task-packages/resume-binding-lifecycle/STATUS.yaml`：把 OR-018 推进到 `detailed_ready` 并补齐验证场景、代码落点和测试落点。
- `docs/task-packages/resume-binding-lifecycle/01-requirements.md`：关闭产品语义讨论，明确 `/resume` 是持久恢复入口。
- `docs/task-packages/resume-binding-lifecycle/02-overview-design.md`：记录系统边界、主流程、失败模式和取舍。
- `docs/task-packages/resume-binding-lifecycle/03-detailed-design.md`：记录测试优先路径、实现落点、接口契约、迁移顺序和残余风险。
- `docs/task-packages/resume-binding-lifecycle/04-verification.md`：记录本轮验证计划和当前验证缺口。
- `docs/task-packages/resume-binding-lifecycle/05-evidence.md`：记录本轮证据索引。

## Commands
- `uv run /home/Shaokun.Tang/.agents/skill-hub/openharness/skills/project-memory/scripts/query_memory.py "018 任务 推进 task package"`
- `uv run openharness bootstrap`
- `uv run python - <<'PY' ... PY`：检查本地 `lark_oapi` card action SDK model 字段。
- `uv run pytest tests/runtime/test_command_router_resume.py tests/session/test_scope_resolver.py tests/runtime/test_reply_policy.py tests/feishu/test_parsing.py`，结果 28 passed。
- `uv run openharness check-tasks`，结果通过，验证 8 个 task package。`final verification command`

## Artifact Paths
- 无新增外部产物。
- 后续真实运行证据应优先写入 `~/.openrelay/data/openrelay.sqlite3` 对应 trace 查询结果，而不是仓库内 `data/openrelay.sqlite3`。

## Follow-ups
- 进入实施阶段时，优先补 native-session 级并发风险的测试或明确风险接受边界。
- 真实飞书服务可用后，补连续 resume 两条后端会话并分别回复成功消息的 trace 证据。
- 单独开启入口治理任务处理关闭、归档、清理、数量上限和复用提示。
