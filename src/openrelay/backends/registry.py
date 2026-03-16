from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BackendDescriptor:
    name: str
    transport: str
    summary: str
    experimental: bool = False


def build_builtin_backend_descriptors() -> dict[str, BackendDescriptor]:
    return {
        "codex": BackendDescriptor(
            name="codex",
            transport="cli-app-server",
            summary="persistent CLI backend via app-server protocol",
        ),
        "claude": BackendDescriptor(
            name="claude",
            transport="cli-json",
            summary="CLI backend via one-shot JSON output",
            experimental=True,
        ),
    }
