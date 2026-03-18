from __future__ import annotations

import re
from datetime import datetime
from typing import Any


STREAMING_ELEMENT_ID = "streaming_content"
LOADING_ELEMENT_ID = "loading_icon"
DEFAULT_THINKING_TEXT = "Executing"
PROCESS_LOG_PANEL_TITLE = "Execution Log"
LOADING_ICON_IMAGE_KEY = "img_v3_02vb_496bec09-4b43-4773-ad6b-0cdd103cd2bg"
REASONING_PREFIX = "Reasoning:\n"


def strip_invalid_image_keys(text: str) -> str:
    if "![" not in text:
        return text

    def replace(match: re.Match[str]) -> str:
        value = match.group(2)
        if value.startswith("img_") or value.startswith("http://") or value.startswith("https://"):
            return match.group(0)
        return value

    return re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", replace, text)


def optimize_markdown_style(text: object, card_version: int = 2) -> str:
    try:
        raw = str(text or "")
        mark = "___CB_"
        code_blocks: list[str] = []

        def replace_code_block(match: re.Match[str]) -> str:
            code_blocks.append(match.group(0))
            return f"{mark}{len(code_blocks) - 1}___"

        rendered = re.sub(r"```[\s\S]*?```", replace_code_block, raw)

        if re.search(r"^#{1,3} ", raw, flags=re.MULTILINE):
            rendered = re.sub(r"^#{2,6} (.+)$", r"##### \1", rendered, flags=re.MULTILINE)
            rendered = re.sub(r"^# (.+)$", r"#### \1", rendered, flags=re.MULTILINE)

        if card_version >= 2:
            rendered = re.sub(r"^(#{4,5} .+)\n{1,2}(#{4,5} )", r"\1\n<br>\n\2", rendered, flags=re.MULTILINE)
            rendered = re.sub(r"^([^|\n].*)\n(\|.+\|)", r"\1\n\n\2", rendered, flags=re.MULTILINE)
            rendered = re.sub(r"\n\n((?:\|.+\|[^\S\n]*\n?)+)", r"\n\n<br>\n\n\1", rendered)
            rendered = re.sub(r"((?:^\|.+\|[^\S\n]*\n?)+)", r"\1\n<br>\n", rendered, flags=re.MULTILINE)
            rendered = re.sub(r"^((?!#{4,5} )(?!\*\*).+)\n\n(<br>)\n\n(\|)", r"\1\n\2\n\3", rendered, flags=re.MULTILINE)
            rendered = re.sub(r"^(\*\*.+)\n\n(<br>)\n\n(\|)", r"\1\n\2\n\n\3", rendered, flags=re.MULTILINE)
            rendered = re.sub(r"(\|[^\n]*\n)\n(<br>\n)((?!#{4,5} )(?!\*\*))", r"\1\2\3", rendered, flags=re.MULTILINE)
            for index, block in enumerate(code_blocks):
                rendered = rendered.replace(f"{mark}{index}___", f"\n<br>\n{block}\n<br>\n")
        else:
            for index, block in enumerate(code_blocks):
                rendered = rendered.replace(f"{mark}{index}___", block)

        rendered = re.sub(r"\n{3,}", "\n\n", rendered)
        return strip_invalid_image_keys(rendered)
    except Exception:
        return str(text or "")


def extract_thinking_content(text: object) -> str:
    value = str(text or "")
    if not value:
        return ""
    scan_re = re.compile(r"<\s*(/?)\s*(?:think(?:ing)?|thought|antthinking)\s*>", re.IGNORECASE)
    result = []
    last_index = 0
    in_thinking = False
    for match in scan_re.finditer(value):
        index = match.start()
        if in_thinking:
            result.append(value[last_index:index])
        in_thinking = match.group(1) != "/"
        last_index = match.end()
    if in_thinking:
        result.append(value[last_index:])
    return "".join(result).strip()


def strip_reasoning_tags(text: object) -> str:
    value = str(text or "")
    stripped = re.sub(r"<\s*(?:think(?:ing)?|thought|antthinking)\s*>[\s\S]*?<\s*/\s*(?:think(?:ing)?|thought|antthinking)\s*>", "", value, flags=re.IGNORECASE)
    stripped = re.sub(r"<\s*(?:think(?:ing)?|thought|antthinking)\s*>[\s\S]*$", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"<\s*/\s*(?:think(?:ing)?|thought|antthinking)\s*>", "", stripped, flags=re.IGNORECASE)
    return stripped.strip()


def clean_reasoning_prefix(text: object) -> str:
    cleaned = re.sub(r"^Reasoning:\s*", "", str(text or ""), flags=re.IGNORECASE)
    return "\n".join(re.sub(r"^_(.+)_$", r"\1", line) for line in cleaned.splitlines()).strip()


def split_reasoning_text(text: object) -> tuple[str, str]:
    value = str(text or "")
    if not value.strip():
        return "", ""
    trimmed = value.strip()
    if trimmed.startswith(REASONING_PREFIX) and len(trimmed) > len(REASONING_PREFIX):
        return clean_reasoning_prefix(trimmed), ""
    tagged_reasoning = extract_thinking_content(value)
    stripped_answer = strip_reasoning_tags(value)
    if not tagged_reasoning and stripped_answer == value:
        return "", value
    return tagged_reasoning or "", stripped_answer or ""


def format_reasoning_duration(milliseconds: object) -> str:
    try:
        seconds = max(0.0, float(milliseconds or 0)) / 1000
    except Exception:
        return "Thought"
    if seconds <= 0:
        return "Thought"
    if seconds < 60:
        return f"Thought for {seconds:.1f}s"
    minutes, remainder = divmod(seconds, 60)
    return f"Thought for {int(minutes)}m {round(remainder)}s"


def first_non_empty_line(text: object) -> str:
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def normalize_inline(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def shorten_inline(text: object, max_length: int = 120) -> str:
    value = normalize_inline(text)
    if len(value) <= max_length:
        return value
    return f"{value[: max_length - 3]}..."


def _wrap_code_words(text: object, *, words_per_line: int = 6, max_lines: int = 4) -> list[str]:
    tokens = str(text or "").replace("`", "'").split()
    if not tokens:
        return []
    chunks = [
        " ".join(tokens[index : index + words_per_line])
        for index in range(0, len(tokens), words_per_line)
    ]
    visible_chunks = chunks[:max_lines]
    if len(chunks) > max_lines and visible_chunks:
        visible_chunks[-1] = f"{visible_chunks[-1]} ..."
    return [f"`{chunk}`" for chunk in visible_chunks if chunk]


def _append_tree_lines(lines: list[str], text: object) -> None:
    raw_lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not raw_lines:
        return
    lines.append(f"└ {raw_lines[0]}")
    lines.extend(f"  {line}" for line in raw_lines[1:])


def _split_detail_lines(text: object, *, code: bool = False, max_lines: int = 6, max_length: int = 120) -> list[str]:
    normalized_lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not normalized_lines:
        return []
    visible_lines = normalized_lines[:max_lines]
    hidden = max(0, len(normalized_lines) - len(visible_lines))
    result: list[str] = []
    for line in visible_lines:
        rendered = shorten_inline(line.replace("`", "'"), max_length)
        result.append(f"`{rendered}`" if code else rendered)
    if hidden > 0:
        result.append(f"... +{hidden} lines")
    return result


def _append_tree_entries(lines: list[str], entries: list[list[str]]) -> None:
    normalized_entries = [entry for entry in entries if entry]
    if not normalized_entries:
        return
    for index, entry in enumerate(normalized_entries):
        is_last = index == len(normalized_entries) - 1
        branch = "└" if is_last else "├"
        continuation = " " if is_last else "│"
        lines.append(f"{branch} {entry[0]}")
        for line in entry[1:]:
            lines.append(f"{continuation} {line}")


def _append_plain_entries(lines: list[str], entries: list[list[str]]) -> None:
    normalized_entries = [entry for entry in entries if entry]
    if not normalized_entries:
        return
    for entry in normalized_entries:
        lines.extend(entry)


def _append_command_block(lines: list[str], command_lines: list[str], detail_entries: list[list[str]]) -> None:
    if command_lines:
        lines.append("│")
        lines.extend(f"│ {line}" for line in command_lines)
    _append_plain_entries(lines, detail_entries)


def _append_plan_block(lines: list[str], detail_entries: list[list[str]]) -> None:
    if not detail_entries:
        return
    lines.append("│")
    _append_plain_entries(lines, detail_entries)


def _join_markdown_lines(lines: list[str]) -> str:
    if not lines:
        return ""
    parts: list[str] = []
    for index, line in enumerate(lines):
        parts.append(line)
        if index == len(lines) - 1:
            continue
        next_line = lines[index + 1]
        if not line or not next_line:
            parts.append("\n")
            continue
        parts.append("  \n")
    return "".join(parts).strip()


def _format_worked_for(started_at: object) -> str:
    raw_value = str(started_at or "").strip()
    if not raw_value:
        return ""
    try:
        started = datetime.fromisoformat(raw_value)
        now = datetime.now(started.tzinfo) if started.tzinfo is not None else datetime.now()
        elapsed_seconds = max(0, int((now - started).total_seconds()))
    except Exception:
        return ""
    minutes, seconds = divmod(elapsed_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    if minutes > 0:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def _normalize_history_title(item: dict[str, Any]) -> str:
    title = normalize_inline(item.get("title"))
    mode = str(item.get("mode") or "").strip()
    if title in {"Explored codebase", "Exploring codebase"}:
        return "Explored" if mode == "exploration" and str(item.get("state") or "") != "running" else "Exploring"
    if title in {"Ran shell command", "Running shell command"}:
        return "Ran" if str(item.get("state") or "") != "running" else "Running"
    if title in {"Searched web", "Searching web"}:
        return "Searched" if str(item.get("state") or "") != "running" else "Searching"
    return title


def _describe_exploration_command(command_text: object) -> str:
    normalized = normalize_inline(command_text)
    if not normalized:
        return ""
    lowered = normalized.lower()
    if lowered.startswith("rg ") or lowered.startswith("grep "):
        detail = re.sub(r"^(?:rg|grep)\s+(?:-[A-Za-z]+\s+)*", "", normalized, count=1).strip()
        return f"Search {detail}" if detail else "Search"
    return normalized


def _describe_web_search_queries(item: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    query = normalize_inline(item.get("query"))
    if query:
        lines.append(f"Search {query}")
    queries = item.get("queries")
    if isinstance(queries, list):
        for entry in queries:
            normalized = normalize_inline(entry)
            rendered = f"Search {normalized}" if normalized else ""
            if rendered and rendered not in lines:
                lines.append(rendered)
    return lines[:4]


def _describe_file_changes(item: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    changes = item.get("changes")
    if not isinstance(changes, list):
        return lines
    for change in changes[:6]:
        if not isinstance(change, dict):
            continue
        path = normalize_inline(change.get("path"))
        if not path:
            continue
        kind = change.get("kind") if isinstance(change.get("kind"), dict) else {}
        change_type = normalize_inline(kind.get("type"))
        if change_type == "add":
            lines.append(f"Add `{path}`")
            continue
        if change_type == "delete":
            lines.append(f"Delete `{path}`")
            continue
        if change_type == "update":
            moved_to = normalize_inline(kind.get("move_path"))
            lines.append(f"Edit `{path}`" if not moved_to else f"Move `{path}` -> `{moved_to}`")
            continue
        lines.append(path)
    return lines


def _describe_collab_targets(item: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    agents = item.get("agents")
    if isinstance(agents, dict):
        for key in agents:
            normalized = normalize_inline(key)
            if normalized and normalized not in labels:
                labels.append(normalized)
    receiver_thread_ids = item.get("receiver_thread_ids")
    if isinstance(receiver_thread_ids, list):
        for value in receiver_thread_ids:
            normalized = normalize_inline(value)
            if normalized and normalized not in labels:
                labels.append(normalized)
    return labels[:4]


def _render_plan_step(step: dict[str, Any]) -> str:
    status = normalize_inline(step.get("status")).lower() or "pending"
    label = status if status in {"pending", "in_progress", "completed"} else "pending"
    text = normalize_inline(step.get("step"))
    if not text:
        return ""
    if label == "completed":
        return f"● ~~{text}~~"
    if label == "in_progress":
        return f"◉ In Progress {text}"
    return f"○ {text}"


def _history_item_tone(item: dict[str, Any]) -> str:
    state = str(item.get("state") or "").strip().lower()
    if state == "running":
        return "running"
    if state in {"cancelled", "canceled", "interrupted", "stopped", "skipped"}:
        return "cancelled"
    if state in {"failed", "error"}:
        return "error"
    if str(item.get("type") or "").strip() == "web_search" and state == "completed":
        return "exploration"
    if str(item.get("type") or "").strip() == "command":
        if str(item.get("mode") or "").strip() == "exploration" and state == "completed":
            return "exploration"
        exit_code = item.get("exit_code")
        if isinstance(exit_code, int) and exit_code != 0:
            return "error"
        if str(item.get("mode") or "").strip() == "command" and state == "completed":
            return "success"
    if state == "completed":
        return "success"
    return "neutral"


def _history_item_bullet(item: dict[str, Any], spinner_frame: int) -> str:
    if str(item.get("type") or "").strip() == "plan":
        return "🟣"
    tone = _history_item_tone(item)
    if tone == "running":
        frames = ("⚪", "◯", "⚪", "◯")
        return frames[abs(int(spinner_frame or 0)) % len(frames)]
    if tone == "cancelled":
        return "🟡"
    if tone == "exploration":
        return "🔵"
    if tone == "error":
        return "🔴"
    if tone == "success":
        if str(item.get("type") or "").strip() == "command" and str(item.get("mode") or "").strip() == "command":
            return "🟢"
        return "•"
    return "•"


def _render_history_item(item: dict[str, Any], spinner_frame: int) -> list[str]:
    item_type = str(item.get("type") or "").strip()
    title = _normalize_history_title(item)
    if not item_type:
        return []

    if item_type == "summary":
        summary_text = str(item.get("text") or "").strip()
        if not summary_text:
            return []
        _partial_reasoning, partial_answer = split_reasoning_text(summary_text)
        rendered_summary = optimize_markdown_style(partial_answer or strip_reasoning_tags(summary_text)).strip()
        if not rendered_summary:
            return []
        return ["---", "", rendered_summary]

    if not title:
        return []

    bullet = _history_item_bullet(item, spinner_frame)
    lines = [f"{bullet} **{title}**"]
    detail_entries: list[list[str]] = []

    if item_type == "command":
        command_value = str(item.get("command") or "").strip()
        mode = str(item.get("mode") or "").strip()
        command_lines: list[str] = []
        if mode == "exploration":
            detail = _describe_exploration_command(command_value)
            if detail:
                detail_entries.append([detail])
        else:
            command_lines = _wrap_code_words(command_value)
        exit_code = item.get("exit_code")
        if exit_code is not None and str(item.get("state") or "") != "running" and int(exit_code) != 0:
            detail_entries.append([f"exit {exit_code}"])
        output_preview_lines = _split_detail_lines(item.get("output_preview"), code=False)
        if output_preview_lines:
            detail_entries.append(["--- Output ---"])
            detail_entries.extend([[line] for line in output_preview_lines])
        if mode == "command":
            _append_command_block(lines, command_lines, detail_entries)
        else:
            _append_plain_entries(lines, detail_entries)
        return lines

    if item_type == "web_search":
        detail_entries.extend([[line] for line in _describe_web_search_queries(item)])
        _append_plain_entries(lines, detail_entries)
        return lines

    if item_type == "reasoning":
        reasoning_text = clean_reasoning_prefix(item.get("text"))
        detail_entries.extend([[line] for line in _split_detail_lines(reasoning_text)])
        _append_plain_entries(lines, detail_entries)
        return lines

    if item_type == "file_change":
        detail_entries.extend([[line] for line in _describe_file_changes(item)])
        _append_plain_entries(lines, detail_entries)
        return lines

    if item_type == "plan":
        steps = item.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                rendered_step = _render_plan_step(step)
                if rendered_step:
                    detail_entries.append([rendered_step])
        if not detail_entries:
            detail_entries.extend([[line] for line in _split_detail_lines(item.get("detail"))])
        _append_plan_block(lines, detail_entries)
        return lines

    if item_type == "collab":
        targets = _describe_collab_targets(item)
        if targets:
            lines[0] = f"{lines[0]} `{targets[0]}`"
            for target in targets[1:]:
                detail_entries.append([f"Agent `{target}`"])
        prompt = str(item.get("prompt") or "").strip()
        if prompt:
            detail_entries.extend([[line] for line in _split_detail_lines(prompt)])
        _append_plain_entries(lines, detail_entries)
        return lines

    detail = str(item.get("detail") or "").strip()
    detail_entries.extend([[line] for line in _split_detail_lines(detail)])
    _append_plain_entries(lines, detail_entries)
    return lines


def _should_render_history_item(item: dict[str, Any]) -> bool:
    item_type = str(item.get("type") or "").strip()
    if item_type != "status":
        return True
    title = normalize_inline(item.get("title"))
    return title not in {"Starting Codex", "Connected session"}


def _render_history_items(items: list[dict[str, Any]], spinner_frame: int) -> str:
    blocks: list[str] = []
    for item in items[-12:]:
        if not isinstance(item, dict):
            continue
        if not _should_render_history_item(item):
            continue
        lines = _render_history_item(item, spinner_frame)
        if lines:
            blocks.append(_join_markdown_lines(lines))
    return "\n\n".join(blocks).strip()


def _streaming_history_bullet(item: dict[str, Any]) -> str:
    item_type = str(item.get("type") or "").strip()
    state = str(item.get("state") or "").strip().lower()
    if item_type == "plan":
        return "🟣"
    if item_type == "web_search":
        return "🔵"
    if item_type == "command":
        if isinstance(item.get("exit_code"), int) and int(item.get("exit_code")) != 0:
            return "🔴"
        if str(item.get("mode") or "").strip() == "exploration":
            return "🔵"
        if state == "completed":
            return "🟢"
    if state in {"failed", "error"}:
        return "🔴"
    return "•"


def _render_streaming_history_item(item: dict[str, Any]) -> list[str]:
    item_type = str(item.get("type") or "").strip()
    if not item_type:
        return []
    if item_type == "summary":
        summary_text = str(item.get("text") or "").strip()
        if not summary_text:
            return []
        _partial_reasoning, partial_answer = split_reasoning_text(summary_text)
        rendered_summary = optimize_markdown_style(partial_answer or strip_reasoning_tags(summary_text)).strip()
        if not rendered_summary:
            return []
        return ["---", "", rendered_summary]
    title = _normalize_history_title(item)
    if not title:
        return []

    lines = [f"{_streaming_history_bullet(item)} {title}"]
    detail_entries: list[list[str]] = []

    if item_type == "command":
        command_value = str(item.get("command") or "").strip()
        mode = str(item.get("mode") or "").strip()
        command_lines: list[str] = []
        if mode == "exploration":
            detail = _describe_exploration_command(command_value)
            if detail:
                detail_entries.append([detail])
        else:
            command_lines = _wrap_code_words(command_value)
        exit_code = item.get("exit_code")
        if exit_code is not None and str(item.get("state") or "") != "running" and int(exit_code) != 0:
            detail_entries.append([f"exit {exit_code}"])
        output_preview_lines = _split_detail_lines(item.get("output_preview"), code=False)
        if output_preview_lines:
            detail_entries.append(["--- Output ---"])
            detail_entries.extend([[line] for line in output_preview_lines])
        if mode == "command":
            _append_command_block(lines, command_lines, detail_entries)
        else:
            _append_plain_entries(lines, detail_entries)
        return lines

    if item_type == "web_search":
        detail_entries.extend([[line] for line in _describe_web_search_queries(item)])
        _append_plain_entries(lines, detail_entries)
        return lines

    if item_type == "reasoning":
        detail_entries.extend([[line] for line in _split_detail_lines(clean_reasoning_prefix(item.get("text")))])
        _append_plain_entries(lines, detail_entries)
        return lines

    if item_type == "file_change":
        detail_entries.extend([[line] for line in _describe_file_changes(item)])
        _append_plain_entries(lines, detail_entries)
        return lines

    if item_type == "plan":
        steps = item.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                rendered_step = _render_plan_step(step)
                if rendered_step:
                    detail_entries.append([rendered_step])
        if not detail_entries:
            detail_entries.extend([[line] for line in _split_detail_lines(item.get("detail"))])
        _append_plan_block(lines, detail_entries)
        return lines

    if item_type == "collab":
        targets = _describe_collab_targets(item)
        if targets:
            lines[0] = f"{lines[0]} `{targets[0]}`"
            for target in targets[1:]:
                detail_entries.append([f"Agent `{target}`"])
        prompt = str(item.get("prompt") or "").strip()
        if prompt:
            detail_entries.extend([[line] for line in _split_detail_lines(prompt)])
        _append_plain_entries(lines, detail_entries)
        return lines

    detail_entries.extend([[line] for line in _split_detail_lines(item.get("detail"))])
    _append_plain_entries(lines, detail_entries)
    return lines


def _render_streaming_history_items(items: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for item in items[-12:]:
        if not isinstance(item, dict):
            continue
        if not _should_render_history_item(item):
            continue
        lines = _render_streaming_history_item(item)
        if lines:
            blocks.append(_join_markdown_lines(lines))
    return "\n\n".join(blocks).strip()


def _build_basic_process_panel_text(state: dict[str, Any]) -> str:
    lines: list[str] = []
    heading = str(state.get("heading") or "").strip()
    status = str(state.get("status") or "").strip()
    current_command = str(state.get("current_command") or "").strip()

    if heading:
        lines.append(f"**{heading}**")
    if status and status != heading:
        lines.append(f"> {status}")
    if current_command:
        lines.append(f"> 正在执行：`{current_command}`")

    history = state.get("history") if isinstance(state.get("history"), list) else []
    history_lines = [str(item).strip() for item in history if str(item).strip()]
    if history_lines:
        if lines:
            lines.append("")
        lines.append("**状态**")
        lines.extend(f"- {item}" for item in history_lines[-6:])

    commands = state.get("commands") if isinstance(state.get("commands"), list) else []
    command_lines: list[str] = []
    for command in commands[-4:]:
        if not isinstance(command, dict):
            continue
        command_text = str(command.get("command") or "").strip()
        if not command_text:
            continue
        exit_code = command.get("exitCode")
        preview = first_non_empty_line(command.get("outputPreview") or "")
        line = f"- `{command_text}`"
        if exit_code is not None:
            line += f" · exit {exit_code}"
        if preview:
            line += f"\n  输出：`{preview}`"
        command_lines.append(line)
    if command_lines:
        if lines:
            lines.append("")
        lines.append("**命令**")
        lines.extend(command_lines)

    reasoning_text = str(state.get("reasoning_text") or state.get("last_reasoning") or "").strip()
    if reasoning_text:
        if lines:
            lines.append("")
        lines.append("**补充内容**")
        lines.append(reasoning_text)

    return "\n".join(lines).strip()


def build_process_panel_text(state: dict[str, Any] | None) -> str:
    return render_transcript_markdown(state)


def render_transcript_markdown(state: dict[str, Any] | None, *, include_summary: bool = True) -> str:
    if not isinstance(state, dict):
        return ""
    history_items = state.get("transcript_items") if isinstance(state.get("transcript_items"), list) else state.get("history_items")
    history_items = history_items if isinstance(history_items, list) else []
    rendered_history = _render_history_items(history_items, int(state.get("spinner_frame") or 0))
    worked_for = _format_worked_for(state.get("started_at") or state.get("startedAt"))
    partial_text = str(state.get("partial_text") or "").strip()
    partial_reasoning, partial_answer = split_reasoning_text(partial_text)
    summary_text = optimize_markdown_style(partial_answer or strip_reasoning_tags(partial_text)).strip()
    reasoning_text = clean_reasoning_prefix(partial_reasoning).strip()

    blocks: list[str] = []
    if rendered_history:
        blocks.append(rendered_history)
    if worked_for and rendered_history:
        blocks.append(f"- Worked for {worked_for}")
    if reasoning_text and not rendered_history:
        blocks.append(f"---\n\n💭 **Thinking...**\n\n{reasoning_text}")
    if include_summary and summary_text:
        blocks.append(f"---\n\n{summary_text}")

    transcript = "\n\n".join(block for block in blocks if block).strip()
    if transcript:
        return transcript
    return _build_basic_process_panel_text(state)


def _build_streaming_markdown_element(content: str = "") -> dict[str, Any]:
    return {
        "tag": "markdown",
        "content": content,
        "text_align": "left",
        "text_size": "normal_v2",
        "margin": "0px 0px 0px 0px",
        "element_id": STREAMING_ELEMENT_ID,
    }


def _build_streaming_loading_element() -> dict[str, Any]:
    return {
        "tag": "markdown",
        "content": " ",
        "icon": {
            "tag": "custom_icon",
            "img_key": LOADING_ICON_IMAGE_KEY,
            "size": "16px 16px",
        },
        "element_id": LOADING_ELEMENT_ID,
    }


def _build_process_panel_element(panel_text: object, panel_title: object = PROCESS_LOG_PANEL_TITLE) -> dict[str, Any] | None:
    content = str(panel_text or "").strip()
    if not content:
        return None
    return {
        "tag": "collapsible_panel",
        "expanded": False,
        "header": {
            "title": {"tag": "markdown", "content": str(panel_title or PROCESS_LOG_PANEL_TITLE).strip()},
            "vertical_align": "center",
            "icon": {
                "tag": "standard_icon",
                "token": "down-small-ccm_outlined",
                "size": "16px 16px",
            },
            "icon_position": "follow_text",
            "icon_expanded_angle": -180,
        },
        "border": {"color": "grey", "corner_radius": "5px"},
        "vertical_spacing": "8px",
        "padding": "8px 8px 8px 8px",
        "elements": [
            {
                "tag": "markdown",
                "content": content,
                "text_size": "notation",
            }
        ],
    }


def _streaming_inline_content(live_state: dict[str, Any] | None = None) -> str:
    return render_transcript_markdown(live_state or {})

def build_streaming_card_signature(live_state: dict[str, Any] | None = None) -> tuple[str, str]:
    _ = live_state
    return ("plain", "")


def build_thinking_card_json() -> dict[str, Any]:
    return {
        "schema": "2.0",
        "config": {"streaming_mode": True},
        "body": {
            "elements": [
                _build_streaming_markdown_element(),
                _build_streaming_loading_element(),
            ]
        },
    }


def build_streaming_card_json(live_state: dict[str, Any] | None = None) -> dict[str, Any]:
    content = build_streaming_content(live_state)
    card = build_thinking_card_json()
    card["body"]["elements"][0]["content"] = content
    return card


def build_streaming_content(live_state: dict[str, Any] | None = None) -> str:
    live_state = live_state or {}
    history_items = live_state.get("transcript_items") if isinstance(live_state.get("transcript_items"), list) else live_state.get("history_items")
    history_items = history_items if isinstance(history_items, list) else []
    rendered_history = _render_streaming_history_items(history_items)
    partial_text = str(live_state.get("partial_text") or "").strip()
    partial_reasoning, partial_answer = split_reasoning_text(partial_text)
    summary_text = optimize_markdown_style(partial_answer or strip_reasoning_tags(partial_text)).strip()
    reasoning_text = clean_reasoning_prefix(partial_reasoning).strip()

    blocks: list[str] = []
    if rendered_history:
        blocks.append(rendered_history)
    if reasoning_text and not rendered_history:
        blocks.append(f"---\n\n💭 **Thinking...**\n\n{reasoning_text}")
    if summary_text:
        blocks.append(f"---\n\n{summary_text}")
    return "\n\n".join(block for block in blocks if block).strip()


def build_complete_card(
    text: object,
    *,
    transcript_markdown: object = "",
    panel_text: object = "",
    panel_title: object = PROCESS_LOG_PANEL_TITLE,
) -> dict[str, Any]:
    raw_text = str(text or "").strip() or "回复为空。"
    _extracted_reasoning, extracted_answer = split_reasoning_text(raw_text)
    transcript_content = str(transcript_markdown or "").strip()
    final_answer = extracted_answer or raw_text
    rendered_answer = optimize_markdown_style(final_answer)

    if transcript_content:
        elements: list[dict[str, Any]] = [{"tag": "markdown", "content": transcript_content}]
    else:
        elements = []
        process_panel = _build_process_panel_element(panel_text, panel_title)
        if process_panel is not None:
            elements.append(process_panel)
        elements.append({"tag": "markdown", "content": rendered_answer})
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True, "update_multi": True},
        "body": {"elements": elements},
    }
