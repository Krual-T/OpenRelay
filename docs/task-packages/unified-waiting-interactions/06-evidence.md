# Evidence

## Files
- `docs/task-packages/unified-waiting-interactions/README.md`
- `docs/task-packages/unified-waiting-interactions/STATUS.yaml`
- `docs/task-packages/unified-waiting-interactions/01-requirements.md`
- `docs/task-packages/unified-waiting-interactions/02-overview-design.md`
- `docs/task-packages/unified-waiting-interactions/03-detailed-design.md`
- `docs/task-packages/unified-waiting-interactions/05-verification.md`
- `docs/task-packages/unified-waiting-interactions/06-evidence.md`
- `src/openrelay/presentation/live_turn_view_builder.py`
- `src/openrelay/agent_runtime/models.py`
- `src/openrelay/agent_runtime/reducer.py`
- `src/openrelay/backends/codex_adapter/runtime_projector.py`
- `src/openrelay/feishu/reply_card.py`
- `src/openrelay/feishu/renderers/live_turn_renderer.py`
- `tests/agent_runtime/test_live_turn_registry.py`
- `tests/feishu/test_streaming_content.py`
- `tests/presentation/test_live_turn_presenter.py`
- `tests/backends/codex_adapter/test_mapper.py`

## Commands
- `.agents/skills/openharness/using-openharness/scripts/openharness.py new-design unified-waiting-interactions OR-010 "Unified Waiting Interactions" --owner codex --summary "Unify waiting-for-user states into one Feishu interaction model."`
- `uv run pytest tests/feishu/test_streaming_content.py tests/presentation/test_live_turn_presenter.py tests/feishu/test_reply_card.py`
- `uv run pytest tests/agent_runtime/test_live_turn_registry.py tests/presentation/test_live_turn_presenter.py tests/feishu/test_streaming_content.py tests/feishu/test_reply_card.py`
- `uv run pytest tests/presentation/test_live_turn_presenter.py tests/agent_runtime/test_live_turn_registry.py tests/feishu/test_streaming_content.py tests/feishu/test_reply_card.py tests/backends/codex_adapter/test_mapper.py`
- `uv run pytest tests/feishu/test_streaming_content.py tests/feishu/test_streaming_session.py tests/feishu/test_reply_card.py tests/presentation/test_live_turn_rendering.py`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks`

## Latest Round
- 2026-03-26:
  - 修复首条飞书消息在连接阶段的空白展示：当 streaming transcript 还没有 history / reasoning / answer 时，`build_streaming_content()` 现在会回退到连接标题并渲染三点 spinner。
  - 连接类 `status` 项仍然不会进入常规 transcript 主线，但如果当前只有 `Starting Codex` 这类状态，会被用作 waiting fallback 文案，避免过渡期完全空白。
  - 新增测试覆盖初始 waiting snapshot 和仅有连接状态项两条路径；相关 streaming session / reply card / live turn rendering 回归通过。
  - `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks` 仍因多个 archived package 的历史 placeholder / missing reference 问题失败，这次未处理该独立仓库债务。

## Follow-ups
- Replace this package's placeholder detailed design with implementation-grade file-level design before coding starts.
- Migrate task-board references to point at this package as the canonical task fact source.
- Decide whether the same static commentary rule should also apply to any non-Feishu presentation surfaces that currently render live commentary independently.
- Align `AGENTS.md` / harness manifest / harness CLI so repository verification no longer points at removed `docs/task-packages` roots.
