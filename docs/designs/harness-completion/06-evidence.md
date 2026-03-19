# Evidence

## Files
- `docs/designs/harness-completion/README.md`
- `docs/designs/harness-completion/STATUS.yaml`
- `docs/designs/harness-completion/01-requirements.md`
- `docs/designs/harness-completion/02-overview-design.md`
- `docs/designs/harness-completion/03-detailed-design.md`
- `docs/designs/harness-completion/05-verification.md`
- `docs/designs/harness-completion/06-evidence.md`
- `docs/designs/message-observability/`
- `docs/designs/architecture-refactor/`
- `docs/designs/unified-waiting-interactions/`
- `docs/designs/current-session-control-surface/`
- `docs/designs/asynchronous-lookback-experience/`
- `docs/designs/workspace-shortcuts-and-directory-maintenance/`
- `docs/designs/log-manager/`
- `docs/designs/legacy-design-package-maturation/`
- `docs/archived/legacy/`
- `AGENTS.md`
- `.codex/skills/`
- `.codex/skills/openharness/SKILL.md`
- `.codex/skills/openharness/references/skill-hub.md`
- `.project-memory/`
- `.codex/skills/openharness/scripts/openharness.py`
- `.codex/skills/openharness/tests/test_openharness.py`

## Commands
- `uv run python .codex/skills/openharness/scripts/openharness.py new-design harness-completion OR-016 "Harness Completion And Design Migration" --owner codex --summary "Complete the repo harness by moving design packages under docs, migrating existing designs, and strengthening enforcement and anti-drift checks."`
- `mv designs/harness-foundation docs/designs/`
- `mv designs/harness-completion docs/designs/`
- `uv run python .codex/skills/openharness/scripts/openharness.py new-design message-observability OR-007 "Message Observability" --owner codex --summary "Formalize the landed message observability design as a harness package."`
- `uv run python .codex/skills/openharness/scripts/openharness.py new-design architecture-refactor OR-009 "Architecture Refactor" --owner codex --summary "Formalize the landed architecture refactor design as a harness package."`
- `uv run python .codex/skills/openharness/scripts/openharness.py new-design unified-waiting-interactions OR-010 "Unified Waiting Interactions" --owner codex --summary "Unify waiting-for-user states into one Feishu interaction model."`
- `uv run python .codex/skills/openharness/scripts/openharness.py new-design current-session-control-surface OR-011 "Current Session Control Surface" --owner codex --summary "Consolidate the current-session status and control entrypoint."`
- `uv run python .codex/skills/openharness/scripts/openharness.py new-design asynchronous-lookback-experience OR-012 "Asynchronous Lookback Experience" --owner codex --summary "Make asynchronous return-to-thread review a first-class Feishu experience."`
- `uv run python .codex/skills/openharness/scripts/openharness.py new-design workspace-shortcuts-and-directory-maintenance OR-013 "Workspace Shortcuts And Directory Maintenance" --owner codex --summary "Reduce repeated workspace navigation with high-frequency shortcuts and maintenance flows."`
- `uv run python .codex/skills/openharness/scripts/openharness.py new-design log-manager OR-014 "Log Manager" --owner codex --summary "Unify logger and observability into a structured system debug ledger entrypoint."`
- `uv run python .codex/skills/openharness/scripts/openharness.py new-design legacy-design-package-maturation OR-017 "Legacy Design Package Maturation" --owner codex --summary "Track historical packages that were scaffolded from legacy task notes and still need implementation-grade design completion."`
- `uv run python .codex/skills/openharness/scripts/openharness.py check-designs`
- `uv run python .codex/skills/openharness/scripts/openharness.py bootstrap --all`
- `uv run pytest .codex/skills/openharness/tests/test_openharness.py`
- `python` script to replace `.codex/skills/*` symlinks with vendored directories copied from the current superpowers source
- `python` script to remove `docs/superpowers/plans/2026-03-19-harness-docs-root-migration.md`
- `python` script to collapse multiple harness entrypoints into `.codex/skills/openharness/scripts/openharness.py`
- `mv tests/harness/test_design_harness.py .codex/skills/openharness/tests/test_openharness.py`
- `apply_patch` to fold the local `using-superpowers` entry-skill contract into `.codex/skills/openharness/SKILL.md`, document the cleanup in `references/skill-hub.md`, and pin the contract in `.codex/skills/openharness/tests/test_openharness.py`
- `apply_patch` to update `AGENTS.md` so the repo-level workflow instructions route skill usage through `openharness`, and to extend `.codex/skills/openharness/tests/test_openharness.py` with an `AGENTS.md` contract check
- `uv run python .codex/skills/openharness/scripts/openharness.py check-designs`
- `uv run pytest .codex/skills/openharness/tests/test_openharness.py`

## Follow-ups
- This package now lives under `docs/designs/harness-completion/`; later work should keep the docs-root layout canonical.
- Mature the historical placeholder packages tracked by `OR-017` one by one.
- Add explicit harness-level rejection for wrong-root task artifacts such as `docs/superpowers/plans/*.md` so local-skill adaptation is backed by protocol enforcement.
