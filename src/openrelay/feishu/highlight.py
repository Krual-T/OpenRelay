from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from pygments import lex
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.token import Token
from rich.console import Console
from rich.style import Style
from rich.text import Text

FEISHU_COLOR_RGBS: dict[str, tuple[int, int, int]] = {
    "grey": (143, 149, 158),
    "red": (216, 74, 74),
    "green": (48, 135, 86),
    "orange": (194, 123, 47),
    "yellow": (181, 137, 0),
    "blue": (47, 111, 223),
    "wathet": (63, 136, 197),
    "purple": (107, 95, 210),
    "carmine": (194, 85, 143),
}

LIGHT_CODE_THEME: dict[object, tuple[int, int, int]] = {
    Token.Comment: (120, 128, 140),
    Token.Error: (191, 60, 60),
    Token.Generic.Deleted: (191, 60, 60),
    Token.Generic.Emph: (107, 95, 210),
    Token.Generic.Heading: (120, 128, 140),
    Token.Generic.Inserted: (48, 135, 86),
    Token.Generic.Output: (120, 128, 140),
    Token.Generic.Prompt: (35, 90, 160),
    Token.Generic.Strong: (35, 90, 160),
    Token.Generic.Subheading: (107, 95, 210),
    Token.Keyword: (107, 95, 210),
    Token.Keyword.Namespace: (107, 95, 210),
    Token.Literal.Number: (166, 106, 41),
    Token.Literal.String: (48, 135, 86),
    Token.Name.Attribute: (47, 111, 223),
    Token.Name.Builtin: (107, 95, 210),
    Token.Name.Class: (47, 111, 223),
    Token.Name.Constant: (166, 106, 41),
    Token.Name.Decorator: (194, 85, 143),
    Token.Name.Function: (47, 111, 223),
    Token.Name.Namespace: (35, 90, 160),
    Token.Name.Tag: (191, 60, 60),
    Token.Name.Variable: (194, 85, 143),
    Token.Operator: (132, 139, 149),
    Token.Punctuation: (132, 139, 149),
}

SHELL_THEME_RGBS: dict[str, tuple[int, int, int]] = {
    "command": (47, 111, 223),
    "flag": (107, 95, 210),
    "operator": (132, 139, 149),
    "env": (194, 85, 143),
    "url": (35, 90, 160),
    "path": (63, 136, 197),
    "string": (48, 135, 86),
    "number": (166, 106, 41),
}

COMMAND_OPERATORS = {"|", "&&", "||", ";", "(", ")", "{", "}"}
MUTED_WORDS = ("skipped", "pending", "waiting")
WARNING_WORDS = ("warning", "deprecated", "timeout")
ERROR_WORDS = ("error", "fatal", "traceback", "assertionerror", "exception", "failed", "failure")
SUCCESS_WORDS = ("done", "ok", "success", "passed", "completed", "saved")
PATH_RE = re.compile(r"(?P<path>(?:\.{1,2}/|/|~/?|[A-Za-z]:\\)?[\w.-]+(?:/[\w.-]+)+/?|[\w.-]+\.[A-Za-z0-9_+-]+)")
URL_RE = re.compile(r"https?://[^\s]+")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
DIFF_HEADER_RE = re.compile(r"^(diff --git|index |@@ |\+\+\+ |--- )")
GIT_STATUS_RE = re.compile(r"^(?P<flag>(?!  )[ MADRCU?!]{2})\s+(?P<path>\S.+)$")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
NUMBER_UNIT_RE = re.compile(r"^\d+(?:\.\d+)+[A-Za-z]*$")


def _compile_word_pattern(words: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(
        r"\b(?:" + "|".join(re.escape(word) for word in words) + r")\b",
        re.IGNORECASE,
    )


ERROR_WORD_RE = _compile_word_pattern(ERROR_WORDS)
WARNING_WORD_RE = _compile_word_pattern(WARNING_WORDS)
SUCCESS_WORD_RE = _compile_word_pattern(SUCCESS_WORDS)
MUTED_WORD_RE = _compile_word_pattern(MUTED_WORDS)


EXTENSION_LANGUAGE = {
    ".bash": "bash",
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".css": "css",
    ".go": "go",
    ".h": "c",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".sh": "bash",
    ".sql": "sql",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".txt": "plain_text",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
}

RICH_WRAP_CONSOLE = Console(force_terminal=False, color_system="truecolor", width=200)


@dataclass(frozen=True)
class ShellSegment:
    text: str
    role: str | None = None
    hard_break: bool = False


def render_command_chunks(
    text: object, *, target_length: int = 34, max_lines: int = 4
) -> list[str]:
    command = str(text or "").strip()
    if not command:
        return []
    visible_budget = max(12, target_length - 2)
    wrapped_lines = _wrap_shell_segments(_build_shell_segments(command), visible_budget)
    visible_chunks = [_render_shell_line(line) for line in wrapped_lines[:max_lines]]
    if len(wrapped_lines) > max_lines and visible_chunks:
        visible_chunks[-1] = f"{visible_chunks[-1]} {_font('grey', '...')}"
    return visible_chunks


def render_output_block(
    text: object,
    *,
    command: object = "",
    max_lines: int = 6,
    max_length: int = 120,
) -> str:
    normalized_lines = [
        ANSI_RE.sub("", line.rstrip("\n"))
        for line in str(text or "").splitlines()
        if line.strip()
    ]
    if not normalized_lines:
        return ""
    lexer_name = _infer_output_lexer_name(
        "\n".join(normalized_lines[:max_lines]), str(command or "")
    )
    if lexer_name == "diff":
        visible_lines = normalized_lines
        hidden = 0
        rendered_lines = _render_diff_lines(visible_lines, max_length=max_length)
    else:
        visible_lines = normalized_lines[:max_lines]
        hidden = max(0, len(normalized_lines) - len(visible_lines))
        if lexer_name is not None and lexer_name not in {"plain_text", "text"}:
            rendered_lines = _highlight_with_pygments("\n".join(visible_lines), lexer_name)
        else:
            rendered_lines = [
                _render_output_line(line, max_length=max_length) for line in visible_lines
            ]
    if hidden > 0:
        rendered_lines.append(_font("grey", f"... +{hidden} lines"))
    return "<br>".join(line for line in rendered_lines if line)


def _highlight_with_pygments(text: str, lexer_name: str) -> list[str]:
    try:
        lexer = get_lexer_by_name(lexer_name)
    except Exception:
        lexer = TextLexer()
    lines: list[str] = []
    parts: list[str] = []
    for token_type, value in lex(text, lexer):
        segments = value.split("\n")
        for index, segment in enumerate(segments):
            if segment:
                parts.append(_render_token(token_type, segment))
            if index != len(segments) - 1:
                lines.append("".join(parts) or "&nbsp;")
                parts = []
    if parts or not lines:
        lines.append("".join(parts) or "&nbsp;")
    return lines


def _highlight_single_line_with_pygments(
    text: str,
    lexer_name: str,
    *,
    default_color: str | None = None,
) -> str:
    try:
        lexer = get_lexer_by_name(lexer_name)
    except Exception:
        lexer = TextLexer()
    parts: list[str] = []
    for token_type, value in lex(text, lexer):
        if not value:
            continue
        parts.append(_render_token(token_type, value, default_color=default_color))
    return "".join(parts) or _font(default_color, text)


def _render_diff_lines(lines: list[str], *, max_length: int) -> list[str]:
    rendered: list[str] = []
    current_lexer: str | None = None
    for line in lines:
        shortened = _shorten(line, max_length)
        if line.startswith("diff --git"):
            current_lexer = _infer_diff_lexer_from_git_header(line) or current_lexer
            rendered.append(_font("wathet", shortened))
            continue
        if line.startswith(("--- ", "+++ ")):
            current_lexer = _infer_diff_lexer_from_marker(line) or current_lexer
            rendered.append(_font("grey", shortened))
            continue
        if line.startswith("@@") or DIFF_HEADER_RE.match(line):
            rendered.append(_font("grey", shortened))
            continue
        if line.startswith("+"):
            rendered.append(
                _render_diff_change_line("green", shortened, lexer_name=current_lexer)
            )
            continue
        if line.startswith("-"):
            rendered.append(
                _render_diff_change_line("red", shortened, lexer_name=current_lexer)
            )
            continue
        rendered.append(_escape(shortened))
    return rendered


def _render_diff_line(line: str, *, max_length: int) -> str:
    shortened = _shorten(line, max_length)
    if (
        line.startswith("+++")
        or line.startswith("---")
        or line.startswith("@@")
        or DIFF_HEADER_RE.match(line)
    ):
        return _font("grey", shortened)
    if line.startswith("+"):
        return _render_diff_change_line("green", shortened)
    if line.startswith("-"):
        return _render_diff_change_line("red", shortened)
    return _font("wathet", shortened) if line.startswith("diff --git") else _escape(shortened)


def _render_diff_change_line(
    color: str,
    text: str,
    *,
    lexer_name: str | None = None,
) -> str:
    prefix = text[:1]
    content = text[1:]
    rendered_prefix = _text_tag(color, prefix)
    if not content:
        return rendered_prefix
    if lexer_name is not None and lexer_name not in {"plain_text", "text"}:
        rendered_content = _highlight_single_line_with_pygments(
            content,
            lexer_name,
            default_color=color,
        )
    else:
        rendered_content = _font(color, content)
    return f"{rendered_prefix}{rendered_content}"


def _render_output_line(line: str, *, max_length: int) -> str:
    shortened = _shorten(line, max_length)
    match = GIT_STATUS_RE.match(shortened)
    if match is not None:
        flag = match.group("flag").strip() or "?"
        path = match.group("path")
        return f"{_font(_git_status_color(flag), flag)} {_highlight_paths(path)}"
    return _render_semantic_line(shortened)


def _render_token(
    token_type: object,
    value: str,
    default_color: str | None = None,
) -> str:
    color = _lookup_color_name(token_type)
    return _font(color or default_color, value)


def _lookup_color_name(token_type: object) -> str | None:
    current = token_type
    while current not in {None, Token}:
        rgb = LIGHT_CODE_THEME.get(current)
        if rgb is not None:
            return _map_rgb_to_feishu(rgb)
        current = getattr(current, "parent", None)
    rgb = LIGHT_CODE_THEME.get(current)
    if rgb is None:
        return None
    return _map_rgb_to_feishu(rgb)


def _build_shell_segments(text: str) -> list[ShellSegment]:
    tokens = _scan_shell_tokens(text)
    if not tokens:
        return []
    segments: list[ShellSegment] = []
    previous_token = ""
    command_position = 0
    for token in tokens:
        if token.isspace():
            segments.extend(_split_shell_whitespace(token))
            continue
        role = _shell_token_role(token, previous_token, command_position)
        segments.extend(_split_shell_token(token, role))
        command_position += 1
        previous_token = token
    return segments


def _build_shell_rich_text(text: str) -> Text:
    rich_text = Text(no_wrap=False, overflow="fold", end="")
    for segment in _build_shell_segments(text):
        rich_text.append(segment.text, style=_shell_rich_style(segment.role))
    return rich_text


def _scan_shell_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character.isspace():
            end = index + 1
            while end < len(text) and text[end].isspace():
                end += 1
            tokens.append(text[index:end])
            index = end
            continue
        if text.startswith(("&&", "||"), index):
            tokens.append(text[index : index + 2])
            index += 2
            continue
        if character in COMMAND_OPERATORS:
            tokens.append(character)
            index += 1
            continue
        if character in {'"', "'"}:
            end = _find_shell_quote_end(text, index)
            tokens.append(text[index:end])
            index = end
            continue
        if character in {">", "<"}:
            end = index + 1
            while end < len(text) and text[end] in {">", "<", "&"}:
                end += 1
            while end < len(text) and text[end].isdigit():
                end += 1
            tokens.append(text[index:end])
            index = end
            continue
        end = index + 1
        while end < len(text):
            next_character = text[end]
            if next_character.isspace():
                break
            if text.startswith(("&&", "||"), end):
                break
            if next_character in COMMAND_OPERATORS or next_character in {'"', "'", ">", "<"}:
                break
            end += 1
        tokens.append(text[index:end])
        index = end
    return tokens


def _find_shell_quote_end(text: str, start: int) -> int:
    quote = text[start]
    index = start + 1
    while index < len(text):
        if text[index] == "\\" and index + 1 < len(text):
            index += 2
            continue
        if text[index] == quote:
            return index + 1
        index += 1
    return len(text)


def _shell_token_role(token: str, previous_token: str, position: int) -> str | None:
    if token in COMMAND_OPERATORS or _looks_like_redirection(token):
        return "operator"
    if token.startswith("-"):
        return "flag"
    if token.startswith("$"):
        return "env"
    if URL_RE.fullmatch(token):
        return "url"
    if token.startswith(('"', "'")) and token.endswith(('"', "'")):
        return "string"
    if PATH_RE.fullmatch(token.strip("\"'")):
        return "path"
    if "=" in token and token.split("=", 1)[0].isidentifier():
        return "env"
    if position == 0 or previous_token in COMMAND_OPERATORS:
        return "command"
    if NUMBER_RE.fullmatch(token):
        return "number"
    return None


def _split_shell_token(token: str, role: str | None) -> list[ShellSegment]:
    if len(token) <= 16 and "\n" not in token and "\r" not in token:
        return [ShellSegment(token, role)]
    parts = re.findall(r"\s+|[^\s]+", token)
    if len(parts) <= 1:
        return [ShellSegment(token, role)]
    segments: list[ShellSegment] = []
    for part in parts:
        if part.isspace():
            segments.extend(_split_shell_whitespace(part, role=role))
            continue
        segments.append(ShellSegment(part, role))
    return segments


def _split_shell_whitespace(token: str, *, role: str | None = None) -> list[ShellSegment]:
    segments: list[ShellSegment] = []
    buffer: list[str] = []
    for character in token:
        if character in "\r\n":
            if buffer:
                segments.append(ShellSegment("".join(buffer), role))
                buffer = []
            segments.append(ShellSegment("", hard_break=True))
            continue
        buffer.append(character)
    if buffer:
        segments.append(ShellSegment("".join(buffer), role))
    return segments


def _wrap_shell_segments(
    segments: list[ShellSegment], target_length: int
) -> list[list[ShellSegment]]:
    if not segments:
        return []
    lines: list[list[ShellSegment]] = []
    current: list[ShellSegment] = []
    current_length = 0

    def flush() -> None:
        nonlocal current, current_length
        trimmed = _trim_shell_line(current)
        if trimmed:
            lines.append(trimmed)
        current = []
        current_length = 0

    for segment in segments:
        if segment.hard_break:
            flush()
            continue
        part_length = len(segment.text)
        if not current and segment.text.isspace():
            continue
        if current and current_length + part_length > target_length:
            flush()
            if segment.text.isspace():
                continue
        current.append(segment)
        current_length += part_length
    flush()
    return lines


def _trim_shell_line(segments: list[ShellSegment]) -> list[ShellSegment]:
    start = 0
    end = len(segments)
    while start < end and segments[start].text.isspace():
        start += 1
    while end > start and segments[end - 1].text.isspace():
        end -= 1
    return segments[start:end]


def _looks_like_redirection(token: str) -> bool:
    return bool(re.fullmatch(r"[<>][<>&0-9]*|[0-9]*[<>][<>&0-9]*|[0-9]*>&[0-9-]+", token))


def _highlight_paths(text: str) -> str:
    return _render_semantic_line(text, only=("path",))


def _render_semantic_line(text: str, *, only: tuple[str, ...] | None = None) -> str:
    if not text:
        return ""
    colors: list[str | None] = [None] * len(text)
    priorities = [-1] * len(text)

    def paint_match(start: int, end: int, color: str, priority: int) -> None:
        for index in range(start, end):
            if priority >= priorities[index]:
                colors[index] = color
                priorities[index] = priority

    groups = set(only or ("url", "path", "number", "error", "warning", "success", "muted"))

    if "url" in groups:
        for match in URL_RE.finditer(text):
            paint_match(match.start(), match.end(), "blue", 60)

    if "path" in groups:
        for match in PATH_RE.finditer(text):
            start, end = match.span("path")
            if not _should_highlight_path(match.group("path")):
                continue
            paint_match(start, end, "wathet", 40)

    if "number" in groups:
        for match in NUMBER_RE.finditer(text):
            paint_match(match.start(), match.end(), "orange", 20)

    if "error" in groups:
        for match in ERROR_WORD_RE.finditer(text):
            paint_match(match.start(), match.end(), "red", 80)

    if "warning" in groups:
        for match in WARNING_WORD_RE.finditer(text):
            paint_match(match.start(), match.end(), "orange", 80)

    if "success" in groups:
        for match in SUCCESS_WORD_RE.finditer(text):
            paint_match(match.start(), match.end(), "green", 80)

    if "muted" in groups:
        for match in MUTED_WORD_RE.finditer(text):
            paint_match(match.start(), match.end(), "grey", 80)

    return _render_colored_segments(text, colors)


def _render_colored_segments(text: str, colors: list[str | None]) -> str:
    parts: list[str] = []
    chunk: list[str] = []
    current_color: str | None = None

    def flush() -> None:
        nonlocal chunk, current_color
        if not chunk:
            return
        segment = "".join(chunk)
        parts.append(_font(current_color, segment) if current_color else _escape(segment))
        chunk = []

    for character, color in zip(text, colors):
        if color != current_color:
            flush()
            current_color = color
        chunk.append(character)
    flush()
    return "".join(parts)


def _infer_output_lexer_name(text: str, command: str) -> str | None:
    stripped = ANSI_RE.sub("", text).strip()
    if not stripped:
        return None
    if _looks_like_diff(stripped):
        return "diff"
    normalized_command = command.lower()
    if "git diff" in normalized_command or "git show" in normalized_command:
        return "diff"
    if normalized_command.startswith(("python ", "uv run python", "python3 ")) and _looks_like_python_source(stripped):
        return "python"
    if normalized_command.startswith(("bash ", "sh ", "zsh ")) and _looks_like_shell_source(stripped):
        return "bash"
    path = _extract_viewed_path(command)
    if path is not None:
        suffix = path.suffix.lower()
        if suffix in EXTENSION_LANGUAGE:
            return EXTENSION_LANGUAGE[suffix]
    return None


def _extract_viewed_path(command: str) -> PurePosixPath | None:
    tokens = [token.strip("\"'") for token in re.findall(r"[^\s]+", command)]
    if len(tokens) < 2:
        return None
    viewer = tokens[0].lower()
    if viewer not in {"cat", "bat", "head", "tail"}:
        return None
    for token in tokens[1:]:
        if token.startswith("-") or "/" not in token and "." not in token:
            continue
        return PurePosixPath(token)
    return None


def _infer_diff_lexer_from_git_header(line: str) -> str | None:
    parts = line.split()
    if len(parts) < 4:
        return None
    for candidate in parts[2:4]:
        lexer_name = _infer_diff_lexer_from_path(candidate)
        if lexer_name is not None:
            return lexer_name
    return None


def _infer_diff_lexer_from_marker(line: str) -> str | None:
    _marker, _space, path = line.partition(" ")
    return _infer_diff_lexer_from_path(path)


def _infer_diff_lexer_from_path(value: str) -> str | None:
    normalized = value.strip().strip("\"'")
    if not normalized or normalized == "/dev/null":
        return None
    if normalized.startswith(("a/", "b/")):
        normalized = normalized[2:]
    suffix = PurePosixPath(normalized).suffix.lower()
    lexer_name = EXTENSION_LANGUAGE.get(suffix)
    if lexer_name in {"plain_text", "text"}:
        return None
    return lexer_name


def _should_highlight_path(value: str) -> bool:
    return not NUMBER_UNIT_RE.fullmatch(value)


def _looks_like_diff(text: str) -> bool:
    lines = text.splitlines()
    if not lines:
        return False
    if any(DIFF_HEADER_RE.match(line) for line in lines[:6]):
        return True
    plus = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
    minus = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))
    return plus > 0 and minus > 0


def _looks_like_python_source(text: str) -> bool:
    return any(
        re.match(
            r"^\s*(def|class|from|import|if|elif|else|for|while|with|return|print)\b",
            line,
        )
        for line in text.splitlines()
        if line.strip()
    )


def _looks_like_shell_source(text: str) -> bool:
    return any(
        re.match(r"^\s*(if|then|fi|for|do|done|case|esac|echo|export)\b", line)
        for line in text.splitlines()
        if line.strip()
    )


def _git_status_color(flag: str) -> str:
    primary = flag[0]
    if primary in {"A", "?"}:
        return "green"
    if primary in {"D", "!"}:
        return "red"
    if primary in {"R", "C", "U"}:
        return "purple"
    return "orange"


def _shorten(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def _render_rich_text_line(line: Text) -> str:
    parts: list[str] = []
    for segment in line.render(RICH_WRAP_CONSOLE):
        if not segment.text:
            continue
        color = _rich_style_to_feishu_color(segment.style)
        parts.append(_font(color, segment.text) if color else _escape(segment.text))
    return "".join(parts).strip()


def _render_shell_line(segments: list[ShellSegment]) -> str:
    rich_text = Text(end="")
    for segment in segments:
        rich_text.append(segment.text, style=_shell_rich_style(segment.role))
    return _render_rich_text_line(rich_text)


def _font(color: str | None, text: str) -> str:
    escaped = _escape(text)
    if not escaped:
        return ""
    if color is None:
        return escaped
    return f"<font color='{color}'>{escaped}</font>"


def _themed_font(role: str | None, text: str) -> str:
    if role is None:
        return _font(None, text)
    rgb = SHELL_THEME_RGBS.get(role)
    return _font(_map_rgb_to_feishu(rgb) if rgb is not None else None, text)


def _shell_rich_style(role: str | None) -> Style | None:
    if role is None:
        return None
    rgb = SHELL_THEME_RGBS.get(role)
    if rgb is None:
        return None
    return Style(color=_rgb_to_hex(rgb))


def _map_rgb_to_feishu(rgb: tuple[int, int, int]) -> str:
    return min(
        FEISHU_COLOR_RGBS.items(),
        key=lambda item: _color_distance(rgb, item[1]),
    )[0]


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _rich_style_to_feishu_color(style: Style | None) -> str | None:
    if style is None or style.color is None or style.color.triplet is None:
        return None
    triplet = style.color.triplet
    return _map_rgb_to_feishu((triplet.red, triplet.green, triplet.blue))


def _color_distance(
    left: tuple[int, int, int], right: tuple[int, int, int]
) -> int:
    return sum((left[index] - right[index]) ** 2 for index in range(3))


def _text_tag(color: str, text: str) -> str:
    escaped = _escape(text)
    if not escaped:
        return ""
    return f"<text_tag color='{color}'>{escaped}</text_tag>"


def _escape(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = escaped.replace(" ", "&nbsp;")
    escaped = escaped.replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
    return escaped
