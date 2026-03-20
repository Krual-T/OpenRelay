# Detailed Design

## Files Added Or Changed
- `.agents/skills/brainstorming/SKILL.md`
  - repo-local generic workflow skill
- `.agents/skills/researching-solutions/SKILL.md`
  - repo-local generic workflow skill with OpenHarness write-back rule compatibility
- `.agents/skills/openharness/researching-solutions/SKILL.md`
  - remove after the generic copy exists
- `.agents/skills/openharness/using-openharness/references/skill-hub.md`
  - recategorize routed workflows vs native gates
- `.agents/skills/openharness/using-openharness/tests/test_openharness.py`
  - assert repo-local generic workflow skills exist in the expected locations

## Interfaces
- `brainstorming` remains a child workflow of `using-openharness`, but its file lives at `.agents/skills/brainstorming/SKILL.md`.
- `researching-solutions` becomes a generic routed workflow at `.agents/skills/researching-solutions/SKILL.md`.
- OpenHarness-native skills remain package- or completion-specific: `using-openharness`, `closing-design-package`, `verification-before-completion`, and `project-memory`.

## Error Handling
- Tests should fail if the repo loses its vendored routed workflow skill copies.
- The OpenHarness hub should not claim that generic workflows are native protocol skills.

## Migration Notes
- This is a classification and vendoring cleanup on top of OR-019; it does not reopen OR-019.
