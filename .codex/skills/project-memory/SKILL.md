---
name: project-memory
description: Reuse and maintain repo-local workflows, facts, and decisions stored under .project-memory/. Use when a codebase question may already have a known reusable answer, when a validated workflow or project fact should be saved for later reuse, or when prompt variants should map to the same memory object without building a central service.
---

# Project Memory

## When To Use
Use this skill when:
- a repeated question like "this API how does it flow" may already have a stored workflow
- a stable project fact like an interface semantic or directory convention should be reused
- a previous architecture or product decision should be reused instead of re-argued
- a successful investigation should be saved as reusable project knowledge
- a new prompt variant should point at an existing workflow instead of duplicating it
- you need to check whether stored knowledge went stale after code changes

## Rules
- Treat `.project-memory/workflows/*.yaml`, `.project-memory/facts/*.yaml`, and `.project-memory/decisions/*.yaml` as the source of truth.
- Treat `.project-memory/index.sqlite` as a disposable cache; rebuild it from YAML when needed.
- Run project-memory scripts with `uv run` from the repo root so they resolve against this repository's managed Python environment.
- `PyYAML` is a required dependency of these scripts and is expected to be available from this project's `pyproject.toml`; if it is missing, fix the project environment instead of falling back to ad-hoc local installs.
- Query memory before re-discovering an already-known workflow, fact, or decision.
- Validate a hit against current files or run `check_stale.py` before relying on it.
- Save only evidence-backed memory objects. Do not store secrets, tokens, or raw chat transcripts.
- Prefer adding aliases to an existing object over creating duplicate objects.
- Treat query results as reusable only when they survive the default score, confidence, and freshness guardrails.
- Save decisions with explicit alternatives, consequences, and a revisit trigger so old choices do not become unquestioned defaults.
- When an object is wrong or superseded, archive or deprecate it instead of deleting it silently.
- After using this skill, reflect on what was missing or unreliable and patch the workflow or aliases when the fix is obvious and low risk.

## Commands
Query known memory objects:

```bash
uv run python .codex/skills/project-memory/scripts/query_memory.py "workspace api 调试流程"
```

Include stale or blocked candidates only when you are explicitly auditing why a result was hidden:

```bash
uv run python .codex/skills/project-memory/scripts/query_memory.py "workspace api 调试流程" --include-unusable
```

Save a validated workflow:

```bash
uv run python .codex/skills/project-memory/scripts/save_workflow.py trace_order_api \
  --title "Trace order create API" \
  --summary "Reusable workflow for following the order create endpoint" \
  --alias "订单创建接口怎么走" \
  --step "Inspect route handler" \
  --step "Inspect service layer" \
  --evidence server/order/order_api.py \
  --evidence server/order/order_service.py \
  --tag api \
  --tag workflow
```

Save a validated fact:

```bash
uv run python .codex/skills/project-memory/scripts/save_fact.py workspace_files_content_semantics \
  --title "workspace/files.content 表示工作区文件内容" \
  --statement "workspace/files.data.content 表示工作区真实文件内容，不是聊天消息文本" \
  --alias "workspace files content 是什么" \
  --applies-to server/deepagents/api.py \
  --evidence docs/design/deepagent/workspace_tree/README.md \
  --tag workspace \
  --tag fact
```

Save a validated decision:

```bash
uv run python .codex/skills/project-memory/scripts/save_decision.py cei_qa_parallel_upgrade_path \
  --title "cei-qa 升级采用并行新增链路" \
  --question "cei-qa 是否应该直接替换旧链路" \
  --decision "不直接替换，保留旧链路并新增新链路" \
  --rationale "降低回归风险并支持独立验证" \
  --alternative "直接在现有链路上继续叠加改动" \
  --consequence "需要短期并行维护两条路径" \
  --revisit-when "当职责边界再次调整时重新评估" \
  --alias "cei-qa 为什么不直接替换旧链路" \
  --evidence docs/design/cei-qa/README.md \
  --tag decision \
  --tag cei-qa
```

Check for stale workflows:

```bash
uv run python .codex/skills/project-memory/scripts/check_stale.py --write-status
```

Audit stale objects, alias collisions, low confidence, and missing metadata:

```bash
uv run python .codex/skills/project-memory/scripts/audit_memory.py
```

Archive or deprecate an incorrect memory object:

```bash
uv run python .codex/skills/project-memory/scripts/archive_memory.py workspace_files_content_semantics \
  --kind fact \
  --status archived \
  --reason "事实已失效，后续不应继续复用" \
  --archived-by codex
```

Deprecate an old object and move its aliases to a replacement:

```bash
uv run python .codex/skills/project-memory/scripts/archive_memory.py workspace_files_content_semantics_v1 \
  --kind fact \
  --status deprecated \
  --reason "已被 v2 取代" \
  --superseded-by workspace_files_content_semantics_v2 \
  --move-aliases-to-superseded
```

## Expected Flow
1. Run `query_memory.py` first.
2. If a memory object matches, inspect its evidence paths or run `check_stale.py`.
3. If no good match exists, investigate normally.
4. If a script fails because a declared dependency is missing, add or repair it in the repo environment before continuing.
5. After the result is validated, save the workflow, fact, or decision with aliases and evidence.
6. If an object is incorrect or replaced, archive it with a reason and optional successor instead of deleting it.
7. Use `audit_memory.py` periodically or when results feel noisy.
8. Reuse the stored object on the next similar question only if it is still reusable under the default guardrails.

## Post-Use Reflection
After using this skill, capture a short `Skill Reflection` that answers:
- Did the query miss a workflow that should have matched because aliases or title were too narrow?
- Did the matched object lack evidence, validation, or freshness checks?
- Which facts, decisions, or workflow steps still had to be rediscovered manually and should be added back into memory?
- Did an old decision or fact remain reusable longer than it should have because it lacked a revisit trigger or owner?
- Should an incorrect or superseded object now be archived or deprecated so it stops showing up in default retrieval?

If the answer is clear, update `.project-memory/` in the same turn instead of leaving the gap for later.
