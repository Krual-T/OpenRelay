from __future__ import annotations

import html
import re
from pathlib import PurePosixPath

from pygments import lex
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.token import Token

CODEX_THEME: dict[object, str] = {
    Token.Comment: "grey",
    Token.Error: "red",
    Token.Generic.Deleted: "red",
    Token.Generic.Emph: "wathet",
    Token.Generic.Heading: "grey",
    Token.Generic.Inserted: "green",
    Token.Generic.Output: "grey",
    Token.Generic.Prompt: "green",
    Token.Generic.Strong: "green",
    Token.Generic.Subheading: "wathet",
    Token.Keyword: "purple",
    Token.Literal.Number: "orange",
    Token.Literal.String: "yellow",
    Token.Name.Attribute: "wathet",
    Token.Name.Builtin: "green",
    Token.Name.Class: "wathet",
    Token.Name.Constant: "orange",
    Token.Name.Function: "wathet",
    Token.Name.Namespace: "wathet",
    Token.Name.Tag: "red",
    Token.Name.Variable: "carmine",
    Token.Operator: "carmine",
    Token.Punctuation: "grey",
}

COMMAND_OPERATORS = {"|", "&&", "||", ";", "(", ")", "{", "}"}
MUTED_WORDS = ("skipped", "pending", "waiting")
WARNING_WORDS = ("warning", "deprecated", "timeout")
ERROR_WORDS = ("error", "fatal", "traceback", "assertionerror", "exception", "failed", "failure")
SUCCESS_WORDS = ("done", "ok", "success", "passed", "completed")
PATH_RE = re.compile(r"(?P<path>(?:\.{1,2}/|/|~/?|[A-Za-z]:\\)?[\w.-]+(?:/[\w.-]+)+/?|[\w.-]+\.[A-Za-z0-9_+-]+)")
URL_RE = re.compile(r"https?://[^\s]+")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
DIFF_HEADER_RE = re.compile(r"^(diff --git|index |@@ |\+\+\+ |--- )")
GIT_STATUS_RE = re.compile(r"^(?P<flag>[ MADRCU?!]{1,2})\s+(?P<path>.+)$")


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


def render_command_chunks(
    text: object, *, target_length: int = 34, max_lines: int = 4
) -> list[str]:
    tokens = _split_command_tokens(str(text or "").strip())
    if not tokens:
        return []
    chunks: list[str] = []
    current_parts: list[str] = []
    current_length = 0
    previous_token = ""
    command_position = 0
    for token in tokens:
        visible = token
        rendered = _style_shell_token(token, previous_token, command_position)
        if token.strip():
            command_position += 1
            previous_token = token
        if current_parts and current_length + len(visible) > target_length:
            chunks.append("".join(current_parts).rstrip())
            current_parts = [rendered]
            current_length = len(visible)
            continue
        current_parts.append(rendered)
        current_length += len(visible)
    if current_parts:
        chunks.append("".join(current_parts).rstrip())
    visible_chunks = chunks[:max_lines]
    if len(chunks) > max_lines and visible_chunks:
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
        line.rstrip("\n") for line in str(text or "").splitlines() if line.strip()
    ]
    if not normalized_lines:
        return ""
    visible_lines = normalized_lines[:max_lines]
    hidden = max(0, len(normalized_lines) - len(visible_lines))
    lexer_name = _infer_output_lexer_name(
        "\n".join(visible_lines), str(command or "")
    )
    if lexer_name == "diff":
        rendered_lines = [
            _render_diff_line(line, max_length=max_length) for line in visible_lines
        ]
    elif lexer_name is not None and lexer_name not in {"plain_text", "text"}:
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
        return _font("green", shortened)
    if line.startswith("-"):
        return _font("red", shortened)
    return _font("wathet", shortened) if line.startswith("diff --git") else _escape(shortened)


def _render_output_line(line: str, *, max_length: int) -> str:
    shortened = _shorten(line, max_length)
    match = GIT_STATUS_RE.match(shortened)
    if match is not None:
        flag = match.group("flag").strip() or "?"
        path = match.group("path")
        return f"{_font(_git_status_color(flag), flag)} {_highlight_paths(path)}"
    lowered = shortened.lower()
    if any(word in lowered for word in ERROR_WORDS):
        return _font("red", shortened)
    if any(word in lowered for word in WARNING_WORDS):
        return _font("orange", shortened)
    if any(word in lowered for word in SUCCESS_WORDS):
        return _font("green", shortened)
    if any(word in lowered for word in MUTED_WORDS):
        return _font("grey", shortened)
    highlighted = _highlight_paths(shortened)
    highlighted = _highlight_urls(highlighted)
    return highlighted


def _render_token(token_type: object, value: str) -> str:
    color = _lookup_color(token_type)
    if color is None:
        return _escape(value)
    return _font(color, value)


def _lookup_color(token_type: object) -> str | None:
    current = token_type
    while current not in {None, Token}:
        color = CODEX_THEME.get(current)
        if color is not None:
            return color
        current = getattr(current, "parent", None)
    return CODEX_THEME.get(current)


def _split_command_tokens(text: str) -> list[str]:
    if not text:
        return []
    return re.findall(r"\s+|[^\s]+", text)


def _style_shell_token(token: str, previous_token: str, position: int) -> str:
    if not token.strip():
        return _escape(token)
    if token in COMMAND_OPERATORS:
        return _font("carmine", token)
    if token.startswith("-"):
        return _font("orange", token)
    if token.startswith("$"):
        return _font("carmine", token)
    if URL_RE.fullmatch(token):
        return _font("blue", token)
    if PATH_RE.fullmatch(token.strip("\"'")):
        return _font("wathet", token)
    if token.startswith(('"', "'")) or token.endswith(('"', "'")):
        return _font("yellow", token)
    if "=" in token and token.split("=", 1)[0].isidentifier():
        name, value = token.split("=", 1)
        return f"{_font('carmine', name)}={_font('yellow', value)}"
    if position == 0 or previous_token in COMMAND_OPERATORS:
        return _font("green", token)
    if token.isdigit():
        return _font("orange", token)
    return _escape(token)


def _highlight_paths(text: str) -> str:
    parts: list[str] = []
    last = 0
    for match in PATH_RE.finditer(text):
        start, end = match.span("path")
        parts.append(_escape(text[last:start]))
        parts.append(_font("wathet", match.group("path")))
        last = end
    parts.append(_escape(text[last:]))
    return "".join(parts)


def _highlight_urls(text: str) -> str:
    if "http://" not in text and "https://" not in text:
        return text
    return URL_RE.sub(lambda match: _font("blue", match.group(0)), text)


def _infer_output_lexer_name(text: str, command: str) -> str | None:
    stripped = ANSI_RE.sub("", text).strip()
    if not stripped:
        return None
    if _looks_like_diff(stripped):
        return "diff"
    path = _extract_command_path(command)
    if path is not None:
        suffix = path.suffix.lower()
        if suffix in EXTENSION_LANGUAGE:
            return EXTENSION_LANGUAGE[suffix]
    normalized_command = command.lower()
    if "git diff" in normalized_command or "git show" in normalized_command:
        return "diff"
    if normalized_command.startswith(("python ", "uv run python", "python3 ")):
        return "python"
    if normalized_command.startswith(("bash ", "sh ", "zsh ")):
        return "bash"
    return None


def _extract_command_path(command: str) -> PurePosixPath | None:
    matches = re.findall(r"(?:^|\s)([\w./-]+\.[A-Za-z0-9_+-]+)", command)
    if not matches:
        return None
    return PurePosixPath(matches[-1].strip("\"'"))


def _looks_like_diff(text: str) -> bool:
    lines = text.splitlines()
    if not lines:
        return False
    if any(DIFF_HEADER_RE.match(line) for line in lines[:6]):
        return True
    plus = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
    minus = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))
    return plus > 0 and minus > 0


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


def _font(color: str, text: str) -> str:
    escaped = _escape(text)
    if not escaped:
        return ""
    return f"<font color='{color}'>{escaped}</font>"


def _escape(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = escaped.replace(" ", "&nbsp;")
    escaped = escaped.replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
    return escaped
