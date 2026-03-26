# Requirements

## Goal
Turn OpenHarness into a reusable agent-first harness system where skills are plug-and-play workflow units, completion is enforced by protocol plus checker gates, and repository-local instructions remain project maps rather than harness specs.

## Problem Statement
The current `using-openharness` skill mixes three roles that should be separate: repository entry routing, repository-specific package walkthrough, and completion enforcement. That makes the entry skill self-referential, makes agent compliance depend too much on prompt wording, and leaves "done" vulnerable to premature claims. At the same time, the harness should not become a closed system; agents must be able to research external solutions and bring them back into the repository in a controlled way.

## Required Outcomes
1. Make `AGENTS.md` a repo-local map only, while OpenHarness owns the reusable harness protocol.
2. Redefine `using-openharness` as the single repository entry skill that routes work instead of re-listing its own activation steps.
3. Define a clear skill taxonomy for harness-native workflow skills, completion gate skills, and reusable general-purpose skills.
4. Treat completion as a protocol state transition that requires verification, evidence, and status updates before the agent may claim success.
5. Allow active external research, but require accepted conclusions to be written into a design package or `.project-memory/`.
6. Add checker support so the completion contract is machine-checkable instead of prompt-only.

## Non-Goals
- Do not redesign the product feature packages unrelated to harness workflow.
- Do not force every reusable engineering skill to become OpenHarness-native.
- Do not eliminate exploratory research; only constrain when it becomes accepted task truth.

## Constraints
- The harness must stay agent-readable and composable rather than turning into a giant monolithic instruction file.
- Existing `docs/task-packages/<task>/` packages remain the task system of record.
- The stricter completion model must coexist with user overrides and repo-local exceptions defined in `AGENTS.md`.
- Verification rules should be enforceable by `openharness.py`, not only described in prose.
