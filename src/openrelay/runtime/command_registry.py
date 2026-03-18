from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from .command_context import CommandContext


class CommandHandler(Protocol):
    async def handle(self, ctx: CommandContext) -> bool: ...


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    aliases: tuple[str, ...] = ()
    requires_admin: bool = False


class CommandRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}
        self._specs: dict[str, CommandSpec] = {}

    def register(self, spec: CommandSpec, handler: CommandHandler) -> None:
        names = (spec.name, *spec.aliases)
        for name in names:
            self._handlers[name] = handler
            self._specs[name] = spec

    def resolve(self, name: str) -> CommandHandler | None:
        return self._handlers.get(name)

    def spec_for(self, name: str) -> CommandSpec | None:
        return self._specs.get(name)
