# Requirements

## Goal
Preserve the landed OR-009 architecture-refactor work as a first-class harness package.

## Problem Statement
The architecture refactor is one of the repository's most important landed design threads, but its historical standalone notes still live under `docs/archived/legacy/` rather than only inside a design package.

## Required Outcomes
1. Package `OR-009` under `docs/archived/legacy/task-packages/architecture-refactor/`.
2. Keep the landed overall design in `02-overview-design.md`.
3. Keep the landed detailed design in `03-detailed-design.md`.
4. Reference the execution blueprint, tests, and implementation evidence from package-local verification/evidence files.

## Non-Goals
- Do not re-run the architecture refactor or redesign its boundaries here.
- Do not delete historical source documents yet.

## Constraints
- Keep the package aligned with the already-landed code and tests.
- Treat the execution blueprint as supporting evidence, not a second primary fact source.
