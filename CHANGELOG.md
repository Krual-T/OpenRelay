# Changelog

## v0.1.0 - 2026-03-18

First public release of `openrelay` as a Feishu-native remote control surface for local coding agents.

### Highlights

- Real backend session resume instead of replaying chat history.
- Thread-first follow-ups inside Feishu conversations.
- Per-directory project context so different workspaces keep different agent habits and boundaries.
- Streaming execution projected back into chat with a stable final reply path.
- Backend-neutral runtime shape with `Codex app-server` as the current main path.

### Core commands

- Session and navigation: `/panel`, `/resume`, `/status`, `/help`
- Workspace switching: `/main`, `/stable`, `/develop`, `/cwd`, `/cd`, `/shortcut`
- Run control: `/stop`, `/clear`, `/model`, `/sandbox`, `/backend`, `/ping`

### Notes

- `Codex` is the main production path today.
- `Claude` is present as a minimal adapter and is not yet feature-parity with `Codex`.
- Promotion assets live in `docs/marketing/` and `static/openrelay_social_card.svg`.
