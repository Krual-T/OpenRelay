# Feishu Card Streaming Window

## Context

Feishu CardKit streaming cards can time out around 10 minutes after streaming starts. If `openrelay` keeps pushing element updates until the platform window expires, the user can see a long-running spinner that ends with `card streaming timeout`, even when the backend turn has already completed.

## Decision

`openrelay` now treats CardKit streaming as a bounded phase instead of an unbounded transport:

- `FEISHU_CARD_STREAMING_WINDOW_SECONDS` controls how long a reply may stay in CardKit `streaming_mode`.
- The default is `540` seconds, leaving roughly one minute of headroom before the observed platform timeout.
- When the window is reached, the current streaming card is proactively switched out of `streaming_mode` and replaced with a static handoff card.
- After that handoff, `openrelay` starts a new streaming card in the same thread and continues live output there.
- When the backend eventually finishes, the latest streaming card is updated with the final reply card.

## Consequences

- Users still get a live card for most replies.
- Long turns no longer depend on Feishu accepting streaming updates for the full backend lifetime.
- If a turn outlives one streaming window, users will see a new continuation card in the same thread instead of a frozen spinner.
- Fast replies still keep the single-card flow unless the turn exceeds the bounded streaming window.
