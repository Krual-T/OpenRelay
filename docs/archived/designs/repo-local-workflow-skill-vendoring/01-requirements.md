# Requirements

## Goal
Make `openrelay` more self-contained by vendoring generic workflow skills that OpenHarness routes into, without turning those workflow skills into OpenHarness-native protocol skills.

## Problem Statement
After OR-019, the repository owns the OpenHarness protocol and a small set of native completion/package skills, but some workflow skills still live only outside the repo. That weakens the repo-local harness story and makes the classification of `researching-solutions` blurry.

## Required Outcomes
1. Vendor `brainstorming` into `.agents/skills/`.
2. Vendor `researching-solutions` into `.agents/skills/` as a generic workflow skill.
3. Keep `using-openharness` as the router and protocol layer rather than absorbing these workflows into native protocol ownership.
4. Update tests and skill-hub documentation to reflect the new routed workflow skill inventory.

## Non-Goals
- Do not redesign OR-019's completion contract.
- Do not move `writing-plans` or `executing-plans`; they are already repo-local.
- Do not turn every generic helper skill into an OpenHarness-native package skill.

## Constraints
- The repo-local copies should remain plain-text skill docs without introducing a second protocol root.
- `researching-solutions` must be classified as routed generic workflow, not native protocol.
