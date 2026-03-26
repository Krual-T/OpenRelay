# Repo-Local Workflow Skill Vendoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vendor repo-local generic workflow skills needed by OpenHarness and clean up their classification.

**Architecture:** Copy the generic workflow skill docs into `.agents/skills/`, remove the misclassified namespaced `researching-solutions`, then update the OpenHarness hub and harness tests so repo-local routing is explicit and durable.

**Tech Stack:** Markdown skill docs, Python 3.12, `uv`, `pytest`

---

### Task 1: Vendor Generic Workflow Skills

**Files:**
- Create: `.agents/skills/brainstorming/SKILL.md`
- Create: `.agents/skills/researching-solutions/SKILL.md`
- Delete: `.agents/skills/openharness/researching-solutions/SKILL.md`
- Test: `uv run --extra dev pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py -q -k "workflow"`

- [ ] Copy `brainstorming` into `.agents/skills/brainstorming/SKILL.md`.
- [ ] Move `researching-solutions` to `.agents/skills/researching-solutions/SKILL.md` and remove the OpenHarness-namespaced copy.
- [ ] Run the focused harness tests and confirm the new paths are recognized.
- [ ] Commit the workflow skill vendoring.

### Task 2: Update Hub, Tests, And Package Evidence

**Files:**
- Modify: `.agents/skills/openharness/using-openharness/references/skill-hub.md`
- Modify: `.agents/skills/openharness/using-openharness/tests/test_openharness.py`
- Modify: `docs/archived/legacy/task-packages/repo-local-workflow-skill-vendoring/05-verification.md`
- Modify: `docs/archived/legacy/task-packages/repo-local-workflow-skill-vendoring/06-evidence.md`
- Modify: `docs/archived/legacy/task-packages/repo-local-workflow-skill-vendoring/STATUS.yaml`

- [ ] Update the skill hub to categorize `brainstorming`, `writing-plans`, and `researching-solutions` as routed workflow skills.
- [ ] Update tests to assert the repo-local routed workflow skills exist in the generic `.agents/skills/` root.
- [ ] Run `check-tasks` and the repo-local harness tests.
- [ ] Update verification/evidence/status and commit the finished package state.

## Verification Gates
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-tasks --repo .`
- `uv run --extra dev pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py -q`

## Commit Plan
- `Vendor repo-local workflow skills`
- `Document repo-local routed workflow skill inventory`
