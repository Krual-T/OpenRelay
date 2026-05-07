# Verification

> 章节标题保留英文；正文默认使用中文；命令、状态值、YAML 键名、文件名与路径保持英文。

## Verification Path
- Planned Path:
  - `openharness check-tasks`
  - `uv run pytest tests/backends/codex_adapter tests/runtime/test_command_router_resume.py -q`
  - `uv run pytest tests/runtime/test_command_router_resume.py tests/session/test_scope_resolver.py tests/runtime/test_reply_policy.py tests/feishu/test_parsing.py`
  - 后续实施或真实验证阶段：真实飞书 `/resume` 卡片连续点击两条后端会话，并回复两条成功消息，用 trace 或 SQLite 查询确认不串线。
- Executed Path:
  - 2026-05-05 已在文档推进前执行 `openharness bootstrap`，确认 OR-018 当时处于 `proposed`，下一步是需求收敛。
  - 2026-05-05 已执行 `uv run pytest tests/runtime/test_command_router_resume.py tests/session/test_scope_resolver.py tests/runtime/test_reply_policy.py tests/feishu/test_parsing.py`，结果 28 passed。
  - 2026-05-05 已执行 `uv run openharness check-tasks`，结果通过，验证 8 个 task package。
  - 2026-05-07 已执行 `uv run pytest tests/backends/codex_adapter/test_app_server.py -q`。先在旧实现上观察到 2 个失败：超长单行 JSON 触发 `LimitOverrunError`，stdout 读取异常直接冒泡且未失败挂起请求；修复后结果为 2 passed。
  - 2026-05-07 已执行 `uv run pytest tests/backends/codex_adapter tests/runtime/test_command_router_resume.py -q`，结果 31 passed。
  - 2026-05-07 已执行真实只读复现：`proxy uv run python - <<'PY' ... transport.read_thread("019dfe0e-91b8-74d2-9128-680f7a419c33", include_turns=True) ... PY`，结果 `read_ok 019dfe0e-91b8-74d2-9128-680f7a419c33 12 /home/Shaokun.Tang/Projects/openrelay notLoaded`。
  - 2026-05-07 已执行 `uv run openharness check-tasks`，结果通过，验证 9 个 task package。
- Path Notes:
  - 2026-05-07 修复的是 `/resume` 卡片点击后进入 Codex app-server 大响应读取时无回复的根因：stdout 不再用 `readline()` 读取整行，读取器异常会重置客户端并让挂起请求失败。
  - 真实飞书连续入口、不串线和 native-session 并发验证尚未完成，因此本包不进入 `archived`。

只有当实现已经完成到足以采集新证据时，才进入 `verifying`。
如果实现仍然延期到后续轮次，就不要使用 `archived`。

## Required Commands
- `openharness check-tasks`
- `uv run pytest tests/backends/codex_adapter tests/runtime/test_command_router_resume.py -q`
- `uv run pytest tests/runtime/test_command_router_resume.py tests/session/test_scope_resolver.py tests/runtime/test_reply_policy.py tests/feishu/test_parsing.py`

## Expected Outcomes
- task package 结构合法。
- Codex app-server stdout 读取器可以处理超过默认 `asyncio` 行限制的 JSON-RPC 单行响应。
- Codex app-server stdout 读取器异常时，挂起的 JSON-RPC 请求会收到失败而不是永久等待。
- 目标测试应通过，覆盖 `/resume` 多入口、成功文案、scope alias、reply policy 和 card action 解析的现有基线。
- 真实验证阶段应看到两个成功回复 message id 分别绑定到不同 `relay_session_id`，且各自后续回复命中对应 `native_session_id`。

## Traceability
- 需求“成功后在哪里继续”：由 `01-requirements.md` 的 `Requirements Closure` 和 `02-overview-design.md` 的 Flow B/C 约束为“回复成功消息继续”。
- 需求“多个恢复入口是否相互独立”：由 `03-detailed-design.md` 的恢复 scope、outbound alias 和目标测试约束。
- 需求“点击连接对话必须有可见结果”：由 `tests/backends/codex_adapter/test_app_server.py` 的大响应读取和异常传播测试，以及 2026-05-07 真实只读 `thread/read` 复现支撑。
- 需求“大量入口如何处理”：本轮明确延期，不作为 `detailed_ready` 阻塞项。
- 风险“同一 native session 并发”：已写入 `02-overview-design.md` 的 failure mode 和 `03-detailed-design.md` 的 execution key 约束。

## Risk Acceptance
- 接受当前没有完成真实飞书连续入口后续回复验证；因此本包不归档。
- 接受入口关闭、归档、清理和数量上限延期；触发条件是用户需要管理大量入口或数据库查询成本显著上升。
- 接受 native-session 级并发保护尚未实现；触发条件是两个本地恢复入口同时运行同一个 `native_session_id`。

## Latest Result
- 2026-05-05：`uv run openharness check-tasks` 通过；目标测试 28 passed。
- 2026-05-07：`uv run openharness check-tasks` 通过，验证 9 个 task package；目标测试 31 passed；真实只读 `thread/read` 复现返回 `read_ok`。
- Latest Artifact: 无。
