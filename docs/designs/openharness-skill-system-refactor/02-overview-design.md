# Overview Design

## System Boundary
This package covers the OpenHarness protocol and skill architecture, not any specific product feature. It governs how agent-led work is routed, what artifacts count as truth, how external research is admitted, and what must happen before work can be declared complete.

## Proposed Structure
- `AGENTS.md` stays repository-local. It maps fact sources, local constraints, and project-specific workflows, but it does not define the reusable harness contract.
- `using-openharness` becomes the reusable entry skill. Once active, it interprets the repo map, locates the relevant design package, and routes into the correct workflow skill.
- OpenHarness-native workflow skills own design and planning phases that write into package artifacts, such as `brainstorming`, `writing-plans`, and a new `researching-solutions` skill.
- Completion gate skills own end-of-task invariants, such as `verification-before-completion`, `project-memory`, and a new `closing-design-package` skill.
- Reusable general-purpose skills such as `systematic-debugging`, `test-driven-development`, `receiving-code-review`, and `subagent-driven-development` remain independent; OpenHarness routes into them when the task needs them, but they are not part of the harness protocol itself.
- `openharness.py` becomes the checker and runtime contract surface for package validation, verification, and completion gating.

## Key Flows
- Entry flow: read `AGENTS.md` as the repo map, resolve the governing package, then let `using-openharness` route into the active workflow skill.
- Design flow: ambiguous work enters `brainstorming`, validated design moves into package docs, then `writing-plans` writes `04-implementation-plan.md` before implementation starts.
- Research flow: external investigation may gather candidate solutions, but accepted conclusions must be written into package docs or `.project-memory/` before they count as repository truth.
- Completion flow: before any completion claim, the harness requires required verification commands, updated `05-verification.md`, updated `06-evidence.md`, and updated `STATUS.yaml`; `openharness.py` checks these invariants.

## Trade-offs
- Splitting routing, workflows, and completion gates across multiple skills adds more moving pieces, but each piece gets a narrower and more enforceable responsibility.
- Checker-backed completion is stricter than prompt-only discipline, but that strictness directly targets the failure mode that matters most: premature "done" claims.
- Allowing research while requiring write-back adds one more step, but it keeps the harness open to new information without letting ephemeral context replace the repository system of record.
