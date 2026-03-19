# Requirements

## Goal
Preserve the landed message observability work as a first-class harness package so observability is represented by the same design protocol as newer tasks.

## Problem Statement
`OR-TASK-007` landed before the repository fully adopted design packages, so its historical standalone design notes still live under `docs/archived/legacy/`. That leaves a split between the actual task facts and the harness package system.

## Required Outcomes
1. Package `OR-007` under `docs/archived/designs/message-observability/`.
2. Keep the landed overall design in `02-overview-design.md`.
3. Keep the landed detailed design in `03-detailed-design.md`.
4. Record the landed verification commands and implementation evidence in package-local files.

## Non-Goals
- Do not redesign the observability solution in this migration task.
- Do not delete the legacy historical notes under `docs/archived/legacy/`.

## Constraints
- Treat this package migration as documentation consolidation, not a behavior change.
- Keep evidence pointing at the already-landed implementation and tests.
