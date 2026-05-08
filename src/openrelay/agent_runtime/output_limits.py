from __future__ import annotations

MAX_TOOL_OUTPUT_DETAIL_CHARS = 65_536
_TOOL_OUTPUT_TRUNCATION_NOTICE = "[openrelay: output truncated; showing tail]"


def bound_tool_output_detail(text: object, *, max_chars: int = MAX_TOOL_OUTPUT_DETAIL_CHARS) -> str:
    value = str(text or "")
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    notice = f"{_TOOL_OUTPUT_TRUNCATION_NOTICE}\n"
    tail_budget = max(max_chars - len(notice), 0)
    return f"{notice}{value[-tail_budget:]}" if tail_budget else notice[:max_chars]


def append_bounded_tool_output_detail(
    existing: object,
    delta: object,
    *,
    max_chars: int = MAX_TOOL_OUTPUT_DETAIL_CHARS,
) -> str:
    existing_text = str(existing or "")
    delta_text = str(delta or "")
    if not existing_text:
        return bound_tool_output_detail(delta_text, max_chars=max_chars)
    if not delta_text:
        return bound_tool_output_detail(existing_text, max_chars=max_chars)
    if len(delta_text) >= max_chars:
        return bound_tool_output_detail(delta_text, max_chars=max_chars)
    return bound_tool_output_detail(f"{existing_text}{delta_text}", max_chars=max_chars)
