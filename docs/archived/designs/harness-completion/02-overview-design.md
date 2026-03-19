# Overview Design

## System Boundary
This task covers the repository-level harness system rather than product runtime code. The scope is:

- where live design packages live
- where legacy material is archived
- what harness validation enforces
- how follow-up historical cleanup is tracked

It does not include building the full future replay engine or workspace/task runtime, but it must leave those with an explicit protocol hook.

## Proposed Structure
The completed harness converges into four layers:

1. `AGENTS.md` as repository map
   - explains where live facts live and what the default workflow is
2. `docs/designs/<task>/` as task fact source
   - each active or long-lived design task becomes a package with fixed documents
3. `.codex/skills/openharness/references/manifest.yaml` plus harness scripts as enforcement entrypoint
   - discovers packages, validates consistency, and runs verification commands
4. `docs/archived/legacy/` as historical archive
   - keeps superseded standalone notes only as legacy evidence

## Key Flows
1. Repository entry
   - agent reads `AGENTS.md`
   - agent reads `.codex/skills/openharness/references/manifest.yaml`
   - agent runs `uv run python .codex/skills/openharness/scripts/openharness.py bootstrap`
   - active packages are discovered from `docs/designs/`

2. Legacy note handling
   - standalone historical notes live under `docs/archived/legacy/`
   - current task facts must live in design packages
   - unresolved package-maturation debt is tracked by a dedicated follow-up package, not by ad-hoc legacy files

3. Harness validation
   - check required files and required status keys
   - check status values against the declared status flow
   - check package path references in `entrypoints` and `evidence`

4. Future completion hook
   - `STATUS.yaml.verification.required_scenarios` remains the attachment point for later replay
   - manifest artifact/task-env roots remain the protocol hook for future execution-system work

## Trade-offs
- Archiving old notes preserves history, but makes package migration non-optional.
- Stronger validation increases friction, but turns harness from advice into enforcement.
- Tracking remaining historical package debt in a dedicated package keeps OR-016 closed without pretending every follow-up task is already implementation-ready.
