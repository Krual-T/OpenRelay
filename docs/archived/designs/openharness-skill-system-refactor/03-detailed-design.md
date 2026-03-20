# Detailed Design

## Files Added Or Changed
- `.agents/skills/openharness/using-openharness/SKILL.md`
  - rewrite as an entry skill and protocol router
- `.agents/skills/openharness/using-openharness/scripts/openharness.py`
  - add checker support for completion gating and accepted-research write-back rules
- `.agents/skills/openharness/using-openharness/references/manifest.yaml`
  - keep artifact contract authoritative and extend it only if new completion metadata is required
- `.agents/skills/openharness/verification-before-completion/SKILL.md`
  - tighten the hard gate so completion claims require checker-backed evidence
- `.agents/skills/openharness/project-memory/SKILL.md`
  - clarify when research conclusions or reusable process knowledge must be persisted
- `.agents/skills/openharness/researching-solutions/SKILL.md`
  - new workflow skill for external solution research and repository write-back
- `.agents/skills/openharness/closing-design-package/SKILL.md`
  - new completion skill for evidence, status updates, and archive decisions

## Interfaces
- Entry contract:
  - `using-openharness` decides whether work belongs to an existing package, a new package, or a repo-level protocol update.
  - It routes to one active workflow skill at a time and always routes through completion gates before completion claims.
- Skill taxonomy:
  - entry skill: `using-openharness`
  - workflow skills: `brainstorming`, `writing-plans`, `researching-solutions`, plus routed general-purpose skills
  - completion gate skills: `verification-before-completion`, `project-memory`, `closing-design-package`
- Completion contract:
  - required commands from `STATUS.yaml.verification.required_commands` must pass
  - `05-verification.md` must record current results
  - `06-evidence.md` must record changed files, commands, and follow-ups
  - `STATUS.yaml` must be updated with the current status and evidence references
  - if the task used external research, the accepted conclusions must appear in package docs or `.project-memory/`
  - only then may the agent describe the work as complete, fixed, or passing
- Checker shape:
  - extend `openharness.py verify` or add a dedicated completion-check subcommand that validates the completion contract for one package or all active packages
  - surface actionable failures, such as missing evidence updates, stale timestamps, empty verification results, or unaccepted research references

## Error Handling
- If no package clearly governs the task, the entry skill must create or select one before implementation.
- If research cannot be grounded into repository artifacts, it remains advisory context and cannot justify a completion claim.
- If verification commands pass but package evidence is stale or incomplete, the checker still fails completion.
- If a user explicitly overrides part of the harness, the override is followed, but the deviation should be documented in package evidence when it affects completion protocol.

## Migration Notes
- Existing repos can keep their local `AGENTS.md` maps with minimal changes because the reusable harness protocol moves into skills and CLI contracts rather than into each repository map.
- Existing general-purpose skills remain reusable; they only need routing guidance, not absorption into OpenHarness.
- Repositories already using the current package structure should migrate mostly by updating skill text and checker behavior, not by changing package layout.
