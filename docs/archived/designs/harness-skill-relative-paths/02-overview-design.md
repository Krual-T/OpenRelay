# Overview Design

## System Boundary
This task only touches the harness workflow surface shared between the external `openharness` skills repository and the `openrelay` repository that consumes those skills through `.agents/skills/openharness`. Runtime product code under `src/openrelay/` is out of scope.

## Proposed Structure
- `../openharness/skills/using-openharness/` becomes the canonical harness-skill implementation. Inside that skill, file references stay relative: `references/manifest.yaml`, `scripts/openharness.py`, and `tests/test_openharness.py`.
- `openrelay` repository documents and design packages use repo-root relative references to the linked skill path: `.agents/skills/openharness/using-openharness/...`.
- The harness CLI gains path resolution that first checks the repo-linked `.agents` layout and then falls back to files adjacent to the script itself.

## Key Flows
1. A collaborator enters `openrelay`, reads `AGENTS.md`, then opens `.agents/skills/openharness/using-openharness/references/manifest.yaml`.
2. The collaborator runs `.agents/skills/openharness/using-openharness/scripts/openharness.py bootstrap` or `check-designs` from the repo root.
3. The CLI loads the manifest from the linked `.agents` skill layout, validates packages, and scaffolds new packages from the skill-local templates.

## Trade-offs
- Keeping repo documents on the explicit `.agents/.../using-openharness/...` path is more verbose than symbolic commands, but it stays runnable without introducing a new wrapper layer.
- Keeping the skill internals relative avoids repeating the skills-root path inside the skill itself and makes the skill portable across repositories.
