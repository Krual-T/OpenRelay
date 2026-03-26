# Evidence

## Files
- `docs/archived/task-packages/harness-completion/README.md`
- `docs/archived/task-packages/harness-completion/STATUS.yaml`
- `docs/archived/task-packages/harness-completion/01-requirements.md`
- `docs/archived/task-packages/harness-completion/02-overview-design.md`
- `docs/archived/task-packages/harness-completion/03-detailed-design.md`
- `docs/archived/task-packages/harness-completion/05-verification.md`
- `docs/archived/task-packages/harness-completion/06-evidence.md`
- `docs/archived/task-packages/message-observability/`
- `docs/archived/task-packages/architecture-refactor/`
- `docs/task-packages/unified-waiting-interactions/`
- `docs/task-packages/current-session-control-surface/`
- `docs/task-packages/asynchronous-lookback-experience/`
- `docs/task-packages/workspace-shortcuts-and-directory-maintenance/`
- `docs/task-packages/log-manager/`
- `docs/task-packages/legacy-design-package-maturation/`
- `docs/archived/legacy/`
- `AGENTS.md`
- `.codex/skills/`
- `.agents/skills/openharness/using-openharness/SKILL.md`
- `.agents/skills/openharness/using-openharness/references/skill-hub.md`
- `.project-memory/`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py`
- `.agents/skills/openharness/using-openharness/tests/test_openharness.py`

## Commands
- `.agents/skills/openharness/using-openharness/scripts/openharness.py new-design harness-completion OR-016 "Harness Completion And Design Migration" --owner codex --summary "Complete the repo harness by moving design packages under docs, migrating existing designs, and strengthening enforcement and anti-drift checks."`
- `mv designs/harness-foundation docs/task-packages/`
- `mv designs/harness-completion docs/task-packages/`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py new-design message-observability OR-007 "Message Observability" --owner codex --summary "Formalize the landed message observability design as a harness package."`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py new-design architecture-refactor OR-009 "Architecture Refactor" --owner codex --summary "Formalize the landed architecture refactor design as a harness package."`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py new-design unified-waiting-interactions OR-010 "Unified Waiting Interactions" --owner codex --summary "Unify waiting-for-user states into one Feishu interaction model."`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py new-design current-session-control-surface OR-011 "Current Session Control Surface" --owner codex --summary "Consolidate the current-session status and control entrypoint."`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py new-design asynchronous-lookback-experience OR-012 "Asynchronous Lookback Experience" --owner codex --summary "Make asynchronous return-to-thread review a first-class Feishu experience."`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py new-design workspace-shortcuts-and-directory-maintenance OR-013 "Workspace Shortcuts And Directory Maintenance" --owner codex --summary "Reduce repeated workspace navigation with high-frequency shortcuts and maintenance flows."`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py new-design log-manager OR-014 "Log Manager" --owner codex --summary "Unify logger and observability into a structured system debug ledger entrypoint."`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py new-design legacy-design-package-maturation OR-017 "Legacy Design Package Maturation" --owner codex --summary "Track historical packages that were scaffolded from legacy task notes and still need implementation-grade design completion."`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py bootstrap --all`
- `pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py`
- `python` script to replace `.codex/skills/*` symlinks with vendored directories copied from the current external skill source
- `python` script to remove the wrong-root planning artifact under the legacy docs root
- `python` script to collapse multiple harness entrypoints into `.agents/skills/openharness/using-openharness/scripts/openharness.py`
- `mv tests/harness/test_design_harness.py .agents/skills/openharness/using-openharness/tests/test_openharness.py`
- `apply_patch` to consolidate the local entry-skill contract into `.agents/skills/openharness/using-openharness/SKILL.md`, document the cleanup in `.agents/skills/openharness/using-openharness/references/skill-hub.md`, and pin the contract in `.agents/skills/openharness/using-openharness/tests/test_openharness.py`
- `apply_patch` to update `AGENTS.md` so the repo-level workflow instructions route skill usage through `openharness`, and to extend `.agents/skills/openharness/using-openharness/tests/test_openharness.py` with an `AGENTS.md` contract check
- `apply_patch` to remove legacy entry-layer names from `.agents/skills/openharness/using-openharness/SKILL.md`, `.agents/skills/openharness/using-openharness/references/skill-hub.md`, and `docs/archived/task-packages/harness-completion/*`
- `python` repository-wide scan for the legacy brand token and its former entry-skill alias
- `apply_patch` to archive `docs/archived/task-packages/harness-completion/` by setting `STATUS.yaml.status` to `archived` and updating package verification notes
- `.agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks`
- `pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py`

## Follow-ups
- This package now lives under `docs/archived/task-packages/harness-completion/`; later work should keep the docs-root layout canonical.
- Mature the historical placeholder packages tracked by `OR-017` one by one.
- Add explicit harness-level rejection for wrong-root task artifacts under deprecated docs roots so local-skill adaptation is backed by protocol enforcement.
