# Overview Design

## System Boundary
This package covers repo-local vendoring and classification of workflow skills, not completion logic or package layout changes.

## Proposed Structure
- Add `.agents/skills/brainstorming/SKILL.md` as a repo-local generic workflow skill.
- Add `.agents/skills/researching-solutions/SKILL.md` as a repo-local generic workflow skill.
- Remove the OpenHarness-namespaced copy of `researching-solutions` so the classification is unambiguous.
- Update the OpenHarness skill hub and harness tests to treat `brainstorming`, `writing-plans`, and `researching-solutions` as routed workflows.

## Key Flows
- `using-openharness` routes ambiguous work to `brainstorming`.
- `using-openharness` routes external investigation to the generic `researching-solutions` workflow.
- OpenHarness-native package and completion gates stay where they are.

## Trade-offs
- Vendoring more generic workflow skills increases repo-local footprint, but it removes an external dependency and makes the harness easier to reuse as a self-contained system.
