# Detailed Design

## Files Added Or Changed
- `AGENTS.md`
  - update repository map so design packages live under `docs/task-packages/`
  - describe migration expectations for legacy `docs/archived/legacy/` content and task-board usage
  - declare `openharness` as the repository-default entry skill so root workflow guidance matches the local skill contract
- `.agents/skills/openharness/using-openharness/references/manifest.yaml`
  - change `designs_root` to `docs/task-packages`
  - keep or refine status flow and artifact roots to match the new structure
- `.agents/skills/openharness/using-openharness/references/templates/*`
  - update scaffolded paths from `designs/<task>/...` to `docs/task-packages/<task>/...`
- `.agents/skills/openharness/using-openharness/scripts/openharness.py`
  - consolidate package discovery, validation, scaffolding, and verification into a single harness CLI
  - `bootstrap` continues package discovery from the new root
  - `check-tasks` expands validation surface beyond file presence
  - `verify` keeps protocol check first, then runs package verification with clearer migration-era reporting
  - `new-task` keeps scaffolding logic inside the skill rather than under the `openrelay` product package
- `.agents/skills/openharness/using-openharness/SKILL.md`
  - own the repository entry-skill duties directly inside the harness skill
  - declare that `openharness` is the only repository entry root for skill checking and routing
- `.agents/skills/openharness/using-openharness/references/skill-hub.md`
  - document that entry-skill behavior now belongs to `openharness`
  - treat duplicated entry layers as protocol drift rather than a supported alias
- `.agents/skills/openharness/using-openharness/tests/test_openharness.py`
  - verify the harness as skill-owned infrastructure instead of product-runtime test surface
  - assert that the repository entry-skill contract is owned by `openharness` rather than a separate parallel layer
  - assert that `AGENTS.md` routes repository skill usage through `openharness`
- `docs/task-packages/<task>/...`
  - new home for migrated and future design packages
- `docs/archived/legacy/`
  - migrate files that represent active or long-lived task designs into package form, or replace them with archival pointers where appropriate
- `docs/task-packages/legacy-design-package-maturation/`
  - track the remaining historical packages that still need implementation-grade design completion
- `.project-memory/facts/*`
  - update any memory object whose evidence or statement still points at the old `designs/` root

## Interfaces
Expected harness-level behavior after this task:

- `load_manifest(repo_root)` resolves `docs/task-packages` as the package root
- `discover_design_packages(...)` only treats package directories under the new root as canonical
- `validate_design_package(package)` reports:
  - missing files
  - missing status keys
  - invalid or unknown status values
  - nonexistent `entrypoints` and `evidence` references
  - other migration-era consistency failures deemed necessary
- `check-tasks` becomes the single protocol gate
- `verify` remains the execution entrypoint for package-declared verification commands
- harness runtime code and its tests live under the harness skill root (`.agents/skills/openharness/using-openharness/SKILL.md`, `scripts/`, `references/`, `tests/`), not under `src/openrelay/` or `tests/`
- `openharness` becomes the repository entry skill for workflow routing, so skill selection starts there before any response or clarifying question

## Error Handling
- The migration should fail loudly when a package points at missing evidence or entrypoint paths.
- During the transition period, drift reports should be explicit rather than silently tolerated.
- If some legacy design documents cannot be migrated in one pass, the repository should record them as deferred follow-ups rather than leaving ambiguous ownership.
- If a future cleanup tries to reintroduce a separate repo entry skill, harness tests should fail so the split-brain workflow does not silently return.

## Migration Notes
- Migrate the current `designs/harness-foundation/` package into `docs/archived/task-packages/harness-foundation/`.
- This package was initially scaffolded under the old root and then migrated with the docs-root move; future packages should be created directly under `docs/task-packages/`.
- Use the following migration classes:
  - `migrate-existing-design`: existing design docs become or are absorbed by a package
  - `package-from-legacy-notes`: no design package exists yet, so scaffold from historical task notes
  - `archive-as-evidence`: keep the document only as historical evidence referenced by a package
  - `derived-index-only`: keep only as a generated or convenience index, never as the primary fact source

## Migration Inventory
### Existing `docs/archived/legacy/` assets
- `docs/archived/legacy/or-task-007-message-observability-design.md`
  - class: `migrate-existing-design`
  - target package: `docs/archived/task-packages/message-observability/`
  - package role: `02-overview-design.md`
- `docs/archived/legacy/or-task-007-message-observability-detailed-design.md`
  - class: `migrate-existing-design`
  - target package: `docs/archived/task-packages/message-observability/`
  - package role: `03-detailed-design.md`
- `docs/archived/legacy/or-task-009-architecture-refactor-overall-design.md`
  - class: `migrate-existing-design`
  - target package: `docs/archived/task-packages/architecture-refactor/`
  - package role: `02-overview-design.md`
- `docs/archived/legacy/or-task-009-architecture-refactor-detailed-design.md`
  - class: `migrate-existing-design`
  - target package: `docs/archived/task-packages/architecture-refactor/`
  - package role: `03-detailed-design.md`
- `docs/archived/legacy/or-task-009-end-to-end-refactor-blueprint.md`
  - class: `migrate-existing-design`
  - target package: `docs/archived/task-packages/architecture-refactor/`
  - package role: supporting execution blueprint referenced from `03-detailed-design.md` or `06-evidence.md`
- `docs/archived/legacy/or-task-014-log-manager-overall-design.md`
  - class: `migrate-existing-design`
  - target package: `docs/task-packages/log-manager/`
  - package role: `02-overview-design.md`

### Historical active-task descriptions
- `OR-TASK-010`
  - class: `package-from-legacy-notes`
  - target package: `docs/task-packages/unified-waiting-interactions/`
  - expected starting state: scaffold package from historical goal, current focus, and close conditions
- `OR-TASK-011`
  - class: `package-from-legacy-notes`
  - target package: `docs/task-packages/current-session-control-surface/`
  - expected starting state: scaffold package from historical task description
- `OR-TASK-012`
  - class: `package-from-legacy-notes`
  - target package: `docs/task-packages/asynchronous-lookback-experience/`
  - expected starting state: scaffold package from historical task description
- `OR-TASK-013`
  - class: `package-from-legacy-notes`
  - target package: `docs/task-packages/workspace-shortcuts-and-directory-maintenance/`
  - expected starting state: scaffold package from historical task description
- `OR-TASK-014`
  - class: `migrate-existing-design`
  - target package: `docs/task-packages/log-manager/`
  - expected starting state: scaffold package and absorb `docs/archived/legacy/or-task-014-log-manager-overall-design.md`
- `OR-TASK-016`
  - class: `already-packaged`
  - target package: `docs/archived/task-packages/harness-completion/`
- `OR-TASK-017`
  - class: `follow-up-package`
  - target package: `docs/task-packages/legacy-design-package-maturation/`
  - expected starting state: track remaining package-maturation debt outside OR-016

### Closed / historical task handling rule
- Closed tasks with only historical value should default to `archive-as-evidence`, not full package backfill.
- Closed tasks whose outputs are still the active architectural fact source may be absorbed into the package of the successor task instead of getting their own new package.
- `OR-TASK-005` should remain archived evidence under the architecture-refactor lineage rather than becoming a new standalone package.

### `docs/archived/legacy/` handling rule
- `docs/archived/legacy/` is the home for superseded standalone documents.
- When an archived document still matters, the owning package should reference it from `06-evidence.md` or migration notes instead of reviving it as a primary design source.

## Enforcement Expansion Plan
`check-tasks` / `validate_design_package(...)` should be extended in this order:

1. `status-flow validation`
   - reject unknown status values
   - optionally validate against `workflow.default_status_flow`
2. `path validation`
   - every `entrypoints` path exists
   - every `evidence.docs/code/tests` path exists
3. `migration drift validation`
   - every canonical `docs/archived/legacy/` asset that still matters is either migrated, referenced by a package, or explicitly left as historical-only evidence
   - remaining historical package-maturation debt is tracked by `OR-017` instead of being left implicit
4. `package freshness validation`
   - active packages should have non-empty `summary`, `done_criteria`, and verification commands or a justified empty state
5. `workflow-root validation`
   - `openharness` is the repository entry skill
   - no separate local entry-layer alias should be treated as canonical

## Delivery Phases
1. `Phase 1: docs-root migration`
   - move package root to `docs/task-packages/`
   - update manifest, tests, templates, repository-map references
2. `Phase 2: package scaffolding and legacy-design absorption`
   - scaffold packages for `OR-TASK-010` to `OR-TASK-014`
   - absorb `OR-TASK-007`, `OR-TASK-009`, `OR-TASK-014` design docs into package structure
3. `Phase 3: anti-drift enforcement`
   - strengthen harness validation and tests
   - make status/path drift visible
4. `Phase 4: protocol completion hooks`
   - document replay, artifact, and task-env contract hooks for future tasks

- Keep this task responsible for defining the migration method and enforcement changes; the migration may be delivered in one or more focused follow-up commits if needed.
