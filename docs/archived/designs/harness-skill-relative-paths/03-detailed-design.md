# Detailed Design

## Files Added Or Changed
- `../openharness/skills/using-openharness/SKILL.md`
  - replace old `.codex`-anchored support-file references with relative `scripts/`, `references/`, and `tests/` paths
  - replace `uv run python ...` command examples with direct `scripts/openharness.py ...` usage
- `../openharness/skills/using-openharness/scripts/openharness.py`
  - add a shebang so the script can run directly
  - resolve `references/manifest.yaml` and `references/templates/` from the linked `.agents` layout or from the script's own neighboring files
  - stop deriving the repo root from a `.codex`-specific manifest path
- `AGENTS.md`
  - update repository-map instructions to the `.agents/skills/openharness/using-openharness/...` layout
  - drop the old `uv run python` command form
- `docs/designs/**` and `docs/archived/designs/**`
  - normalize harness references to the linked `.agents/.../using-openharness/...` path
- `.project-memory/facts/design_packages_are_task_source.yaml`
  - refresh the supporting manifest evidence path

## Interfaces
- Skill-local contract:
  - `references/manifest.yaml`
  - `references/templates/*`
  - `scripts/openharness.py`
  - `tests/test_openharness.py`
- Repo-level runnable entrypoints:
  - `.agents/skills/openharness/using-openharness/scripts/openharness.py bootstrap`
  - `.agents/skills/openharness/using-openharness/scripts/openharness.py check-designs`
  - `.agents/skills/openharness/using-openharness/scripts/openharness.py verify <design>`

## Error Handling
- If the repo-linked `.agents` path is missing, the CLI falls back to manifest and template files adjacent to the script.
- If neither repo-linked nor local manifest/template files exist, the CLI raises a concrete "checked these paths" error instead of failing silently.
- Design-package validation keeps failing loudly on missing referenced files or invalid statuses.

## Migration Notes
- The earlier `.codex` references are treated as protocol drift and removed from both active and archived harness-facing docs.
- No repository wrapper is added in this task; direct repo-root execution still goes through the linked `.agents/skills/openharness/using-openharness/scripts/openharness.py`.
