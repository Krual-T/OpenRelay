"""
Cell → 飞书 Markdown 渲染。

对齐官方 Codex TUI 的视觉约定（颜色、前缀、缩进），
适配飞书 CardKit markdown 语法。
"""

from __future__ import annotations

import re

from openrelay.feishu.highlight import render_command_chunks, render_output_block

from .cells import (
    TOOL_OUTPUT_MAX_LINES,
    USER_SHELL_MAX_LINES,
    AgentMarkdownCell,
    AgentMessageCell,
    CollabAgentCell,
    ErrorCell,
    ExecCell,
    FinalSeparatorCell,
    HookCell,
    McpToolCallCell,
    PatchHistoryCell,
    PlanStepItem,
    PlanUpdateCell,
    ProposedPlanCell,
    ReasoningCell,
    WebSearchCell,
    WarningCell,
)

# ---- spinner & bullets ----------------------------------------------------

SPINNER_FRAMES = ("● • •", "• ● •", "• • ●")

BULLET_SUCCESS = "🟢"
BULLET_FAILURE = "🔴"
BULLET_NEUTRAL = "🟠"
BULLET_INFO = "🔵"


def _bullet(status: str, *, running: bool, spinner_frame: int = 0) -> str:
    if running:
        return SPINNER_FRAMES[spinner_frame % 3]
    if status == "completed":
        return BULLET_SUCCESS
    if status == "failed":
        return BULLET_FAILURE
    return BULLET_SUCCESS


def _dim(text: str) -> str:
    return f"<font color='grey'>{text}</font>"


def _blue(text: str) -> str:
    return f"<font color='blue'>{text}</font>"


def _bold(text: str) -> str:
    return f"**{text}**"


def _code(text: str) -> str:
    text = text.replace("`", "'")
    return f"`{text}`"


def _truncated_marker(hidden: int) -> str:
    return _dim(f"... +{hidden} lines")


def _exploration_command(command: str) -> str:
    """探测性命令（rg/grep/find 等）生成简述文本。"""
    normalized = " ".join(command.split()).strip().lower()
    if not normalized:
        return ""
    for prefix in ("rg ", "grep "):
        if normalized.startswith(prefix):
            detail = re.sub(r"^(?:rg|grep)\s+(?:-[A-Za-z]+\s+)*", "", normalized, count=1).strip()
            return _code(f"Search {detail}") if detail else _code("Search")
    return _code(normalized)


def _command_bullet(cell: ExecCell, *, running: bool, spinner_frame: int) -> str:
    if running:
        return SPINNER_FRAMES[spinner_frame % 3]
    if cell.exit_code is not None and cell.exit_code != 0:
        return BULLET_FAILURE
    if cell.exploration:
        return BULLET_INFO
    return BULLET_SUCCESS


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


# ---- exec cell ------------------------------------------------------------


def render_exec_cell(cell: ExecCell, *, running: bool, spinner_frame: int = 0) -> str:
    bullet = _command_bullet(cell, running=running, spinner_frame=spinner_frame)
    status_text = "Running" if running else "Ran"
    lines: list[str] = []

    if cell.exploration:
        header = f"{bullet} {_bold(status_text)} {_exploration_command(cell.command)}"
        lines.append(header)
    else:
        command_chunks = render_command_chunks(cell.command, target_length=34, max_lines=2)
        if command_chunks:
            header = f"{bullet} {_bold(status_text)} {' '.join(command_chunks)}"
        else:
            header = f"{bullet} {_bold(status_text)} {_code(cell.command)}"
        lines.append(header)

    # exit code
    if not running and cell.exit_code is not None and cell.exit_code != 0:
        lines.append(f"  {_dim(f'exit {cell.exit_code}')}")

    # output — 只在 completed 后一次性展示，不在流式过程中逐行更新
    if not running and cell.output.strip():
        output_lines = cell.output.splitlines()
        visible = [ln.rstrip() for ln in output_lines if ln.strip()]
        max_lines = TOOL_OUTPUT_MAX_LINES if not cell.exploration else USER_SHELL_MAX_LINES
        hidden = max(0, len(visible) - max_lines)
        display_lines = visible[:max_lines]

        if display_lines:
            rendered = render_output_block(
                "\n".join(display_lines), command=cell.command, max_lines=max_lines, max_length=120
            )
            if rendered:
                for idx, line in enumerate(rendered.split("<br>")):
                    prefix = "└" if idx == 0 else " "
                    lines.append(f"  {_dim(prefix)} {_dim(line)}")

        if hidden > 0:
            lines.append(f"  {_truncated_marker(hidden)}")

    return "\n".join(lines)


# ---- mcp tool call cell ---------------------------------------------------


def render_mcp_tool_call_cell(cell: McpToolCallCell, *, running: bool, spinner_frame: int = 0) -> str:
    bullet = _bullet(cell.status, running=running, spinner_frame=spinner_frame)
    status_text = "Calling" if running else "Called"
    invocation = f"{_blue(cell.server)}.{_blue(cell.tool)}" if cell.server and cell.tool else cell.server or cell.tool or "MCP"
    lines = [f"{bullet} {_bold(status_text)} {invocation}"]

    if not running and cell.result:
        result_lines = str(cell.result).splitlines()
        visible = [ln.rstrip() for ln in result_lines if ln.strip()]
        hidden = max(0, len(visible) - TOOL_OUTPUT_MAX_LINES)
        for idx, line in enumerate(visible[:TOOL_OUTPUT_MAX_LINES]):
            prefix = "└" if idx == 0 else " "
            lines.append(f"  {_dim(prefix)} {_dim(line)}")
        if hidden > 0:
            lines.append(f"  {_truncated_marker(hidden)}")

    return "\n".join(lines)


# ---- patch history cell ---------------------------------------------------


def _file_change_tag(color: str, text: str) -> str:
    return f"<text_tag color='{color}'>{text}</text_tag>"


def render_patch_history_cell(cell: PatchHistoryCell, *, running: bool, spinner_frame: int = 0) -> str:
    bullet = _bullet(cell.status, running=running, spinner_frame=spinner_frame)
    status_text = "Updating files" if running else "Updated files"
    lines = [f"{bullet} {_bold(status_text)}"]

    for change in cell.changes[:6]:
        if not isinstance(change, dict):
            continue
        path = " ".join(str(change.get("path") or "").split()).strip()
        if not path:
            continue
        kind = change.get("kind") if isinstance(change.get("kind"), dict) else {}
        change_type = str(kind.get("type") or "").strip()
        if change_type == "add":
            lines.append(f"    {_file_change_tag('green', 'Add')} {_code(path)}")
        elif change_type == "delete":
            lines.append(f"    {_file_change_tag('red', 'Delete')} {_code(path)}")
        elif change_type == "update":
            moved_to = str(kind.get("move_path") or "").strip()
            if moved_to:
                lines.append(f"    {_file_change_tag('blue', 'Move')} {_code(path)} → {_code(moved_to)}")
            else:
                lines.append(f"    {_file_change_tag('orange', 'Edit')} {_code(path)}")

    # diff output — 只在 completed 后展示
    detail = cell.diff or cell.output
    if not running and detail.strip():
        detail_lines = detail.splitlines()
        visible = [ln.rstrip() for ln in detail_lines if ln.strip()]
        hidden = max(0, len(visible) - TOOL_OUTPUT_MAX_LINES)
        if visible:
            rendered = render_output_block(
                "\n".join(visible[:TOOL_OUTPUT_MAX_LINES]), command="git diff", max_lines=TOOL_OUTPUT_MAX_LINES, max_length=120
            )
            if rendered:
                for idx, line in enumerate(rendered.split("<br>")):
                    prefix = "└" if idx == 0 else " "
                    lines.append(f"    {_dim(prefix)} {_dim(line)}")
        if hidden > 0:
            lines.append(f"    {_truncated_marker(hidden)}")

    return "\n".join(lines)


# ---- web search cell ------------------------------------------------------


def render_web_search_cell(cell: WebSearchCell, *, running: bool, spinner_frame: int = 0) -> str:
    bullet = _bullet(cell.status, running=running, spinner_frame=spinner_frame)
    status_text = "Searching web" if running else "Searched web"
    query = cell.query or ""
    return f"{bullet} {_bold(status_text)} {_code(query)}"


# ---- collab agent cell ----------------------------------------------------


def render_collab_agent_cell(cell: CollabAgentCell, *, running: bool, spinner_frame: int = 0) -> str:
    bullet = _bullet(cell.status, running=running, spinner_frame=spinner_frame)
    status_text = "Updating agent" if running else "Updated agent"
    tool = cell.tool or "Collaborative agent"
    lines = [f"{bullet} {_bold(status_text)} {_code(tool)}"]
    for target in cell.targets[:4]:
        lines.append(f"  Agent {_code(target)}")
    if cell.prompt.strip():
        prompt_lines = cell.prompt.splitlines()
        visible = [ln.strip() for ln in prompt_lines if ln.strip()][:3]
        for line in visible:
            lines.append(f"  {_dim(line)}")
    return "\n".join(lines)


# ---- agent message cells --------------------------------------------------


def render_agent_message_cell(cell: AgentMessageCell, *, width: int = 80) -> str:
    """渲染 AgentMessageCell 单行片段。"""
    line = cell.source_line.strip()
    if not line:
        return ""
    if cell.is_first:
        return f"{_dim('•')} {line}"
    return f"  {line}"


def render_agent_markdown_cell(cell: AgentMarkdownCell, *, width: int = 80) -> str:
    """渲染合并后的 AgentMarkdownCell — 直接返回原始 markdown 源。"""
    return cell.source.strip()


# ---- reasoning cell -------------------------------------------------------


def render_reasoning_cell(cell: ReasoningCell) -> str:
    text = cell.text.strip()
    if not text:
        return ""
    return f"💭 {_bold('Thinking...')}\n\n{text}"


# ---- hook cell ------------------------------------------------------------


def render_hook_cell(cell: HookCell, *, running: bool, spinner_frame: int = 0) -> str:
    bullet = _bullet(cell.status, running=running, spinner_frame=spinner_frame)
    hook_type = cell.hook_type or "hook"
    status_text = "Running" if running else "Completed"
    lines = [f"{bullet} {_bold(f'{status_text} {hook_type}')}"]
    for msg in cell.messages:
        lines.append(f"  {_dim(msg)}")
    return "\n".join(lines)


# ---- plan cells -----------------------------------------------------------


def render_plan_update_cell(cell: PlanUpdateCell) -> str:
    lines = [f"{_dim('•')} {_bold('Updated Plan')}"]
    if cell.explanation.strip():
        lines.append(f"  {_dim(cell.explanation.strip())}")
    if cell.steps:
        for step in cell.steps:
            icon = {"pending": "○", "in_progress": "◉", "completed": "●"}.get(step.status, "○")
            if step.status == "completed":
                lines.append(f"  {icon} ~~{step.step}~~")
            elif step.status == "in_progress":
                lines.append(f"  {_bold(f'{icon} {step.step}')}")
            else:
                lines.append(f"  {_dim(f'{icon} {step.step}')}")
    else:
        lines.append(f"  {_dim('(no steps)')}")
    return "\n".join(lines)


def render_proposed_plan_cell(cell: ProposedPlanCell) -> str:
    source = cell.source.strip()
    if not source:
        return f"{_dim('•')} {_bold('Proposed Plan')}"
    return f"{_dim('•')} {_bold('Proposed Plan')}\n\n  {source}"


# ---- notification cells ---------------------------------------------------


def render_warning_cell(cell: WarningCell) -> str:
    return f"⚠️ {cell.message}"


def render_error_cell(cell: ErrorCell) -> str:
    return f"🔴 {cell.message}"


# ---- separator cell -------------------------------------------------------


def render_final_separator_cell(cell: FinalSeparatorCell) -> str:
    parts = []
    if cell.elapsed_seconds >= 60:
        parts.append(f"Worked for {_format_duration(cell.elapsed_seconds)}")
    if cell.metrics:
        parts.append(cell.metrics)
    if not parts:
        return _dim("─" * 20)
    return _dim(f"─ {' • '.join(parts)} ─")
