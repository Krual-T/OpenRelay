from __future__ import annotations

from .command_context import ParsedCommand


class CommandParser:
    def parse(self, text: str) -> ParsedCommand | None:
        raw = text.strip()
        if not raw.startswith("/"):
            return None
        parts = raw.split(maxsplit=1)
        return ParsedCommand(
            name=parts[0].lower(),
            arg_text=parts[1].strip() if len(parts) > 1 else "",
            raw_text=raw,
        )
