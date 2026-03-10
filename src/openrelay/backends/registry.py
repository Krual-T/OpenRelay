from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from openrelay.backends.base import Backend
from openrelay.backends.codex import CodexBackend
from openrelay.config import AppConfig


@dataclass(slots=True)
class BackendDescriptor:
    name: str
    transport: str
    summary: str
    factory: Callable[[AppConfig], Backend]
    experimental: bool = False



def build_builtin_backend_descriptors() -> dict[str, BackendDescriptor]:
    return {
        "codex": BackendDescriptor(
            name="codex",
            transport="cli-app-server",
            summary="persistent CLI backend via app-server protocol",
            factory=lambda config: CodexBackend(
                config.backend.codex_cli_path,
                config.backend.default_model,
                request_timeout_seconds=config.backend.codex_request_timeout_seconds,
            ),
        ),
    }



def instantiate_builtin_backends(config: AppConfig, descriptors: dict[str, BackendDescriptor] | None = None) -> dict[str, Backend]:
    selected = descriptors or build_builtin_backend_descriptors()
    return {name: descriptor.factory(config) for name, descriptor in selected.items()}
