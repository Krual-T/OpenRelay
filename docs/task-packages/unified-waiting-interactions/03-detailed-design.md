# Detailed Design

## Files Added Or Changed
- `docs/task-packages/unified-waiting-interactions/README.md`
  - package entrypoint
- `docs/task-packages/unified-waiting-interactions/STATUS.yaml`
  - machine-readable task state
- `docs/task-packages/unified-waiting-interactions/01-requirements.md`
  - package-local task framing derived from legacy task notes
- `docs/task-packages/unified-waiting-interactions/02-overview-design.md`
  - current high-level structure
- `docs/task-packages/unified-waiting-interactions/03-detailed-design.md`
  - placeholder for next implementation-grade design pass

## Interfaces
- This package is currently a harness entrypoint for future work, not yet an implementation-ready design.
- Future detailed design should identify the exact modules, state transitions, and verification plan for this task.

## Commentary Rendering Adjustment
- `src/openrelay/agent_runtime/models.py` / `src/openrelay/agent_runtime/reducer.py`
  - commentary 不再保存为单独的 `commentary_text` 或 `commentary_items` 文本槽位。
  - commentary 改为结构化 record，按 backend `item_id` 做增量 upsert 与 completed 收口，和其他实时 activity 一样进入 runtime 主线。
- `src/openrelay/presentation/live_turn_view_builder.py`
  - builder 直接把 commentary record 转成 `history_items` / `transcript_items`，不再依赖独立 commentary 通道。
  - transcript merge 按 `commentary_id` 保留多条 commentary，避免只剩最后一条。
- `src/openrelay/feishu/reply_card.py`
  - streaming transcript 直接渲染 `commentary` item，使其和 `Searching` / `Ran` 一样按线性 transcript 实时追加。
  - commentary 不再显示固定标签，而是渲染为分割线 `---` 加正文的分段。
- `src/openrelay/feishu/renderers/live_turn_renderer.py`
  - final card 直接复用 transcript 渲染结果；commentary 已经在 transcript 主线里，不再需要独立补拼。

## Verification Notes
- waiting/streaming 阶段：
  - commentary 应与 `Searching` / `Ran` 一样出现在 streaming card 中，并按 transcript 顺序线性追加。
  - commentary 不应带 `Update` 或其他固定标签，应以分割线分段方式出现。
- final reply 阶段：
  - commentary 应作为静态 transcript 条目出现在 process panel 中。
  - commentary 与 `Ran` / `Searched` 等历史项保持同级。
  - 如果一个 turn 中产生多条 completed commentary，最终卡片必须保留全部条目，不能只保留最后一条。
  - commentary 位于最终答复正文之前。

## Error Handling
- Until a full detailed design exists, this package should not imply implementation readiness.
- Follow-up work should replace this placeholder with file-level design before coding starts.

## Migration Notes
- This package is scaffolded from historical task notes that no longer serve as a live source of truth.
- Future iterations should gradually move the task's canonical design details fully into this package.
