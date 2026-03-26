# Overview Design

## System Boundary
This package covers historical package-maturation debt, not product implementation.

## Proposed Structure
- `OR-010` through `OR-013` remain first-class packages.
- Their next implementation-grade design passes should be tracked from this package until each one is ready to proceed independently.
- `OR-014` is excluded because it already has a package-local overall design and a direct detailed-design follow-up.

## Key Flows
- enumerate packages that were scaffolded from historical notes
- decide which one should receive the next detailed-design pass
- update the package itself rather than reviving standalone notes

## Trade-offs
- A dedicated follow-up package adds one more artifact, but keeps OR-016 truly completable.
- It also makes the remaining debt explicit instead of leaving it implied in multiple placeholder packages.
