# Requirements

## Goal
Complete the repository harness so it is the real default system for task design, migration, verification, and anti-drift governance.

## Problem Statement
`OR-015` established the harness foundation, but the repository still had three kinds of split-brain facts:

- current design packages under `docs/designs/`
- standalone historical design notes outside package structure
- legacy task-tracking material that had not yet been fully absorbed into packages

This meant the repository had a harness schema, but not yet a complete harness working system.

## Required Outcomes
1. Move the design-package root into `docs/` so the repository's design material has one consistent home.
2. Archive old standalone design notes under `docs/archived/legacy/` and stop treating them as live fact sources.
3. Formalize active and high-value historical tasks as design packages.
4. Strengthen harness validation so it checks protocol consistency, not only file presence.
5. Track unresolved historical package-maturation work in a dedicated follow-up package instead of leaving it implicit.
6. Document the next-stage protocol for replay/artifact/task-env integration so the harness can evolve toward a more complete execution system.

## Non-Goals
- Do not implement a full scenario replay engine in this task.
- Do not implement full worktree or task-environment orchestration in this task.
- Do not finish the implementation-grade detailed design for every active package in this task.

## Constraints
- Keep the repository workflow centered on `AGENTS.md`, `.codex/skills/openharness/references/manifest.yaml`, and package-local documents.
- Preserve historical material under `docs/archived/legacy/`, but never treat it as the current source of truth.
- Any stronger enforcement must remain simple enough to run through `uv run ...` inside this repository.
