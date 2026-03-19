# OpenHarness Skill System Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make OpenHarness repo-local and protocol-first by rewriting the entry skill, introducing workflow/completion-gate skill boundaries, and adding checker-backed completion validation.

**Architecture:** Vendor the OpenHarness assets into this repository under `.agents/skills/openharness/`, then tighten the protocol at two levels: skill text for routing and hard gates, and `openharness.py` for machine-checkable completion validation. Keep `AGENTS.md` as the repo map while design packages and `.project-memory/` remain the accepted truth sinks.

**Tech Stack:** Markdown skill docs, Python 3.12, `uv`, `pytest`, YAML-backed design packages

---

### Task 1: Vendor OpenHarness Into The Repository

**Files:**
- Create: `.agents/skills/openharness/using-openharness/SKILL.md`
- Create: `.agents/skills/openharness/using-openharness/references/manifest.yaml`
- Create: `.agents/skills/openharness/using-openharness/references/skill-hub.md`
- Create: `.agents/skills/openharness/using-openharness/references/templates/design-package.README.md`
- Create: `.agents/skills/openharness/using-openharness/references/templates/design-package.STATUS.yaml`
- Create: `.agents/skills/openharness/using-openharness/references/templates/design-package.01-requirements.md`
- Create: `.agents/skills/openharness/using-openharness/references/templates/design-package.02-overview-design.md`
- Create: `.agents/skills/openharness/using-openharness/references/templates/design-package.03-detailed-design.md`
- Create: `.agents/skills/openharness/using-openharness/references/templates/design-package.04-implementation-plan.md`
- Create: `.agents/skills/openharness/using-openharness/references/templates/design-package.05-verification.md`
- Create: `.agents/skills/openharness/using-openharness/references/templates/design-package.06-evidence.md`
- Create: `.agents/skills/openharness/using-openharness/scripts/openharness.py`
- Create: `.agents/skills/openharness/using-openharness/tests/test_openharness.py`
- Modify: `AGENTS.md`
- Test: `uv run pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py -q`

- [ ] **Step 1: Copy the current OpenHarness support files into `.agents/skills/openharness/using-openharness/`**

```bash
mkdir -p .agents/skills/openharness/using-openharness/{references/templates,scripts,tests}
cp /home/Shaokun.Tang/Projects/openharness/skills/using-openharness/SKILL.md .agents/skills/openharness/using-openharness/SKILL.md
cp /home/Shaokun.Tang/Projects/openharness/skills/using-openharness/references/manifest.yaml .agents/skills/openharness/using-openharness/references/manifest.yaml
cp /home/Shaokun.Tang/Projects/openharness/skills/using-openharness/references/skill-hub.md .agents/skills/openharness/using-openharness/references/skill-hub.md
cp /home/Shaokun.Tang/Projects/openharness/skills/using-openharness/references/templates/* .agents/skills/openharness/using-openharness/references/templates/
cp /home/Shaokun.Tang/Projects/openharness/skills/using-openharness/scripts/openharness.py .agents/skills/openharness/using-openharness/scripts/openharness.py
cp /home/Shaokun.Tang/Projects/openharness/skills/using-openharness/tests/test_openharness.py .agents/skills/openharness/using-openharness/tests/test_openharness.py
```

- [ ] **Step 2: Update `AGENTS.md` to point at the vendored repo-local OpenHarness paths consistently**

Run: `rg -n "openharness|\.agents/skills/openharness" AGENTS.md`
Expected: every harness reference points at `.agents/skills/openharness/using-openharness/...`

- [ ] **Step 3: Run the copied tests to see the first failure mode**

Run: `uv run pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py -q`
Expected: FAIL on stale path assumptions or missing repo-local skills, giving the first implementation target

- [ ] **Step 4: Commit the vendored baseline**

```bash
git add AGENTS.md .agents/skills/openharness/using-openharness
git commit -m "Vendor OpenHarness assets into openrelay"
```

### Task 2: Rewrite Skill Boundaries Around Entry, Workflow, And Completion Gates

**Files:**
- Modify: `.agents/skills/openharness/using-openharness/SKILL.md`
- Create: `.agents/skills/openharness/researching-solutions/SKILL.md`
- Create: `.agents/skills/openharness/closing-design-package/SKILL.md`
- Modify: `.agents/skills/openharness/verification-before-completion/SKILL.md`
- Modify: `.agents/skills/openharness/project-memory/SKILL.md`
- Modify: `docs/designs/openharness-skill-system-refactor/03-detailed-design.md`
- Test: `uv run pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py -q -k "skill or entry"`

- [ ] **Step 1: Vendor the dependent skill docs that OR-019 now treats as OpenHarness-native**

```bash
mkdir -p .agents/skills/openharness/{verification-before-completion,project-memory,researching-solutions,closing-design-package}
cp /home/Shaokun.Tang/Projects/openharness/skills/verification-before-completion/SKILL.md .agents/skills/openharness/verification-before-completion/SKILL.md
cp /home/Shaokun.Tang/Projects/openharness/skills/project-memory/SKILL.md .agents/skills/openharness/project-memory/SKILL.md
```

- [ ] **Step 2: Rewrite `using-openharness` into a protocol router instead of a self-referential checklist**

Key text to land:
```md
## Responsibilities
OpenHarness decides:
- which package governs the task
- which workflow skill should run now
- which completion gates must run before completion claims
```

- [ ] **Step 3: Add `researching-solutions` and `closing-design-package` with hard write-back/completion rules**

Key rules to land:
```md
- External research is only accepted after it is written into package docs or `.project-memory/`.
- A package cannot be closed until verification, evidence, and status are updated.
```

- [ ] **Step 4: Tighten the existing completion-related skills to match the new completion contract**

Run: `uv run pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py -q -k "skill or entry"`
Expected: PASS for skill-text assertions after updating or replacing the stale expectations

- [ ] **Step 5: Commit the skill-boundary rewrite**

```bash
git add .agents/skills/openharness docs/designs/openharness-skill-system-refactor/03-detailed-design.md
git commit -m "Refactor OpenHarness skill boundaries"
```

### Task 3: Add Checker-Backed Completion Validation

**Files:**
- Modify: `.agents/skills/openharness/using-openharness/scripts/openharness.py`
- Modify: `.agents/skills/openharness/using-openharness/tests/test_openharness.py`
- Modify: `.agents/skills/openharness/using-openharness/references/manifest.yaml`
- Test: `uv run pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py -q`

- [ ] **Step 1: Write failing tests for the completion contract**

Add tests that cover:
```python
def test_completion_check_fails_when_verification_doc_is_placeholder(): ...
def test_completion_check_fails_when_evidence_doc_is_placeholder(): ...
def test_completion_check_fails_when_status_timestamp_is_stale(): ...
def test_completion_check_accepts_research_only_after_write_back(): ...
```

- [ ] **Step 2: Run the focused tests to confirm the checker does not exist yet**

Run: `uv run pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py -q -k "completion_check or write_back"`
Expected: FAIL because the parser and validation logic do not yet implement the completion contract

- [ ] **Step 3: Extend `openharness.py` with a completion-check path**

Minimal interface to add:
```python
completion_parser = subparsers.add_parser("check-completion", help="Validate whether a design package may be declared complete.")
completion_parser.add_argument("design", nargs="?", default="")
completion_parser.add_argument("--repo", default=".")
```

Validation rules to implement:
```python
if package.status_name not in {"verifying", "archived"}:
    errors.append("completion check requires verifying or archived status")
if _looks_placeholder(package.root / "05-verification.md"):
    errors.append("verification document still looks like a placeholder")
if _looks_placeholder(package.root / "06-evidence.md"):
    errors.append("evidence document still looks like a placeholder")
```

- [ ] **Step 4: Re-run the full harness tests**

Run: `uv run pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py -q`
Expected: PASS with the new parser choice and completion-check behavior covered

- [ ] **Step 5: Commit the checker work**

```bash
git add .agents/skills/openharness/using-openharness
git commit -m "Add OpenHarness completion checker"
```

### Task 4: Update Package Evidence, Project Memory, And Final Verification

**Files:**
- Modify: `docs/designs/openharness-skill-system-refactor/04-implementation-plan.md`
- Modify: `docs/designs/openharness-skill-system-refactor/05-verification.md`
- Modify: `docs/designs/openharness-skill-system-refactor/06-evidence.md`
- Modify: `docs/designs/openharness-skill-system-refactor/STATUS.yaml`
- Create or Modify: `.project-memory/facts/openharness_completion_contract.yaml`
- Test: `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-designs --repo .`
- Test: `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py verify OR-019 --repo .`
- Test: `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-completion OR-019 --repo .`

- [ ] **Step 1: Record the verification commands and latest results in the design package**

Run: `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py verify OR-019 --repo .`
Expected: PASS and concrete command output ready to copy into `05-verification.md`

- [ ] **Step 2: Record changed files, commands, and follow-ups in `06-evidence.md`**

Key evidence block to include:
```md
## Commands
- `uv run pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py -q`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-completion OR-019 --repo .`
```

- [ ] **Step 3: Persist the reusable completion rule to project memory**

Create `.project-memory/facts/openharness_completion_contract.yaml` with fields for the rule, scope, and source package `OR-019`.

- [ ] **Step 4: Set the package status to `verifying`, then run the completion gate**

Run: `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-completion OR-019 --repo .`
Expected: PASS only after `05-verification.md`, `06-evidence.md`, and `STATUS.yaml` all reflect the implementation results

- [ ] **Step 5: Commit the verified implementation state**

```bash
git add docs/designs/openharness-skill-system-refactor .project-memory .agents/skills/openharness
git commit -m "Implement OpenHarness protocol-first skill system"
```

## Verification Gates
- `uv run pytest .agents/skills/openharness/using-openharness/tests/test_openharness.py -q`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-designs --repo .`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py verify OR-019 --repo .`
- `uv run .agents/skills/openharness/using-openharness/scripts/openharness.py check-completion OR-019 --repo .`

## Commit Plan
- `Vendor OpenHarness assets into openrelay`
- `Refactor OpenHarness skill boundaries`
- `Add OpenHarness completion checker`
- `Implement OpenHarness protocol-first skill system`
