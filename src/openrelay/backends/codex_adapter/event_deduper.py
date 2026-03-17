from __future__ import annotations

from .semantic_events import CodexSemanticEvent


class CodexSemanticDeduper:
    def accept(self, event: CodexSemanticEvent, state: object) -> bool:
        terminal = getattr(state, "terminal", None)
        if event.terminal_kind:
            if terminal is None:
                return True
            if terminal.closed:
                return False
            terminal.closed = True
            terminal.terminal_kind = event.terminal_kind
            terminal.source_route = event.source_route
            terminal.source_method = event.source_method
            return True

        dedupe_key = event.dedupe_key
        if not dedupe_key:
            return True
        seen = getattr(state, "seen_semantic_keys", None)
        if seen is None:
            return True
        if dedupe_key in seen:
            return False
        seen.add(dedupe_key)
        return True

