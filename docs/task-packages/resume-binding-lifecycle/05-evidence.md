# Evidence

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Residual Risks
- 真实飞书后续回复验证尚未在本包内完成；当前状态不能支撑 `archived`。
- 同一个 backend `native_session_id` 被多个本地会话同时运行时，是否需要 native-session 级串行化仍是实施阶段风险。
- 恢复入口关闭、归档、清理、数量上限和复用提示已延期，长期入口治理仍需后续任务承接。

## Manual Steps
- 本轮未执行真实飞书人工点击验证。
- 2026-05-07 执行了真实 Codex app-server 只读复现，读取目标 thread `019dfe0e-91b8-74d2-9128-680f7a419c33`，观察到 `read_ok` 返回。
- 后续真实验证建议：发送 `/resume`，连续点击两条不同后端会话，分别回复两条成功消息，再用 trace 或 SQLite 查询对应关系。

## Files
- `docs/task-packages/resume-binding-lifecycle/README.md`：更新任务状态说明。
- `docs/task-packages/resume-binding-lifecycle/STATUS.yaml`：把 OR-018 推进到 `detailed_ready` 并补齐验证场景、代码落点和测试落点。
- `docs/task-packages/resume-binding-lifecycle/01-requirements.md`：关闭产品语义讨论，明确 `/resume` 是持久恢复入口。
- `docs/task-packages/resume-binding-lifecycle/02-overview-design.md`：记录系统边界、主流程、失败模式和取舍。
- `docs/task-packages/resume-binding-lifecycle/03-detailed-design.md`：记录测试优先路径、实现落点、接口契约、迁移顺序和残余风险。
- `docs/task-packages/resume-binding-lifecycle/04-verification.md`：记录本轮验证计划和当前验证缺口。
- `docs/task-packages/resume-binding-lifecycle/05-evidence.md`：记录本轮证据索引。
- `src/openrelay/backends/codex_adapter/app_server.py`：把 Codex app-server stdout 从整行读取改为分块读取；读取器异常时重置客户端并失败挂起请求。
- `src/openrelay/runtime/turn_run_controller.py`：为流式卡片增加稳定文本判断，避免 freeze 后仅因 spinner 动画变化而 rollover 出新的重复卡片。
- `tests/backends/codex_adapter/test_app_server.py`：新增大 JSON-RPC 单行响应和 stdout 读取器异常传播的回归测试。
- `tests/runtime/test_turn.py`：新增 freeze 后 spinner-only 不 rollover、稳定内容变化仍可 rollover 的回归测试。

## Commands
- `uv run /home/Shaokun.Tang/.agents/skill-hub/openharness/skills/project-memory/scripts/query_memory.py "018 任务 推进 task package"`
- `uv run openharness bootstrap`
- `uv run python - <<'PY' ... PY`：检查本地 `lark_oapi` card action SDK model 字段。
- `uv run pytest tests/runtime/test_command_router_resume.py tests/session/test_scope_resolver.py tests/runtime/test_reply_policy.py tests/feishu/test_parsing.py`，结果 28 passed。
- `uv run openharness check-tasks`，结果通过，验证 8 个 task package。
- `uv run pytest tests/backends/codex_adapter/test_app_server.py -q`，旧实现先失败 2 项；修复后结果 2 passed。
- `uv run pytest tests/backends/codex_adapter tests/runtime/test_command_router_resume.py -q`，结果 31 passed。
- `uv run pytest tests/runtime/test_turn.py tests/runtime/test_command_router_resume.py tests/backends/codex_adapter tests/feishu/test_streaming_session.py -q`，结果 45 passed。
- `curl -I --max-time 5 https://chatgpt.com`，直接连接 5 秒超时；随后按网络约定使用 `proxy` 执行真实只读复现。
- `bash -ilc 'proxy uv run python - <<'PY' ... transport.read_thread("019dfe0e-91b8-74d2-9128-680f7a419c33", include_turns=True) ... PY'`，结果 `read_ok 019dfe0e-91b8-74d2-9128-680f7a419c33 12 /home/Shaokun.Tang/Projects/openrelay notLoaded`。
- `uv run openharness check-tasks`，结果通过，验证 9 个 task package。`final verification command`

## Artifact Paths
- 无新增外部产物。
- 真实运行库证据来自 `~/.openrelay/data/openrelay.sqlite3`，相关点击链路为 `trace_12bb847a2ceb407b`，卡片点击 message id 为 `om_x100b50833da638a0c3b63b9dc0b64b2`。
- 后续真实运行证据应优先写入 `~/.openrelay/data/openrelay.sqlite3` 对应 trace 查询结果，而不是仓库内 `data/openrelay.sqlite3`。

## Follow-ups
- 进入实施阶段时，优先补 native-session 级并发风险的测试或明确风险接受边界。
- 真实飞书服务可用后，补连续 resume 两条后端会话并分别回复成功消息的 trace 证据。
- 单独开启入口治理任务处理关闭、归档、清理、数量上限和复用提示。
