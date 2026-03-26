# Verification

## Required Commands
- `.agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks`
- `uv run pytest tests/feishu/test_streaming_content.py tests/presentation/test_live_turn_presenter.py tests/feishu/test_reply_card.py`
- `uv run pytest tests/presentation/test_live_turn_presenter.py tests/agent_runtime/test_live_turn_registry.py tests/feishu/test_streaming_content.py tests/feishu/test_reply_card.py tests/backends/codex_adapter/test_mapper.py`

## Expected Outcomes
- The active task now exists as a formal harness package.
- Future implementation work can use this package as the task entrypoint.

## Latest Result
- 2026-03-19: package scaffolded from historical task notes and promoted to a formal harness package.
- 2026-03-26: commentary 分段从 `---` 切换为 `<br>• 文本`；验证覆盖 streaming transcript、reply transcript 和 final process panel，确认 commentary 与后续 command block 在同一卡片里保持显式断行。
- 2026-03-26: commentary waiting behavior adjusted so commentary 与 `Searching` / `Ran` 一样进入线性 transcript 主线；streaming 阶段实时追加，final reply 保留完整 transcript。同轮验证覆盖 streaming content、final card transcript 和 reply card rendering。
- 2026-03-26: commentary 渲染调整落地时，仓库协议仍残留 `docs/designs` / `check-designs` 表述，后续已统一迁回 `docs/task-packages` / `check-tasks`。
- 2026-03-26: commentary 已完全并入结构化 transcript 主线，不再依赖独立的 `commentary_text` / `commentary_items` 通道；同一 turn 中的多条 commentary 现在按 `commentary_id` 保留并与 `Ran` / `Searched` 同级渲染。
- 2026-03-26: 首条消息连接阶段的 streaming card 不再空白；当还没有 reasoning、tool 或 answer 时，卡片会回退到 `Starting Codex` 或当前 heading，并显示三点 spinner 过渡。验证覆盖初始 waiting snapshot、连接状态项回退，以及相关 Feishu streaming/reply 渲染链。
