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
  - commentary 不再显示固定标签，而是渲染为显式换行前缀 `<br>• 文本`，避免 Feishu 对 `---` 分隔线与后续 command block 连续排版时出现视觉上“没换行”的粘连。
- `src/openrelay/feishu/renderers/live_turn_renderer.py`
  - final card 直接复用 transcript 渲染结果；commentary 已经在 transcript 主线里，不再需要独立补拼。

## Initial Connecting Transition
- `src/openrelay/feishu/reply_card.py`
  - streaming card 在 `history_items`、`reasoning_text`、`partial_text` 都还为空时，不再返回空串。
  - 若当前只有被 transcript 过滤掉的连接类 `status` 条目，例如 `Starting Codex`，则优先复用该标题，配合 spinner dots 渲染过渡文本。
  - 若尚未收到连接状态事件，则退回当前 snapshot 的 `heading` / `status`，至少保证首条飞书消息在连接阶段显示 `● • •` 动效而不是空白。
- `tests/feishu/test_streaming_content.py`
  - 覆盖初始 waiting snapshot 和仅有 `Starting Codex` 状态项这两类空白入口，确保连接阶段 spinner 过渡稳定存在。

## Spinner Ordering
- `src/openrelay/feishu/reply_card.py`
  - 仅对 running 态的三点 spinner 调整标题拼接顺序：从 `● • • Searching` 改为 `Searching ● • •`。
  - 静态状态图标如 `🟣 Plan`、`🟢 Ran shell command` 继续保留前置，不与 spinner 排版规则混用。
  - waiting fallback 也与 running transcript 对齐，统一为 `Generating reply ● • •`、`Starting Codex • ● •` 这类“状态在前、spinner 在后”的顺序。
- `tests/feishu/test_streaming_content.py` / `tests/feishu/test_reply_card.py`
  - 覆盖 streaming transcript、初始 waiting fallback、连接状态 fallback，以及 final transcript 中 running command 的新顺序，防止后续回退。

## Verification Notes
- waiting/streaming 阶段：
  - commentary 应与 `Searching` / `Ran` 一样出现在 streaming card 中，并按 transcript 顺序线性追加。
  - commentary 不应带 `Update` 或其他固定标签，应以分割线分段方式出现。
  - 首条消息连接 Codex 时，即使尚未进入 reasoning / tool / answer，也必须显示 spinner dots 过渡，不能出现空白卡片。
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
