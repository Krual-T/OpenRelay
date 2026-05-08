"""
卡牌构建器 — 从 TurnV2State 构建飞书 CardKit JSON。

Streaming card: schema 2.0, streaming_mode: true, 单 markdown element
Final card: schema 2.0, update_multi: true, 可选 collapsible_panel
"""

from __future__ import annotations

from .cell_renderer import (
    SPINNER_FRAMES,
    _dim,
    render_agent_markdown_cell,
    render_collab_agent_cell,
    render_error_cell,
    render_exec_cell,
    render_final_separator_cell,
    render_hook_cell,
    render_mcp_tool_call_cell,
    render_patch_history_cell,
    render_plan_update_cell,
    render_proposed_plan_cell,
    render_reasoning_cell,
    render_warning_cell,
    render_web_search_cell,
)
from .cells import (
    AgentMarkdownCell,
    AgentMessageCell,
    CollabAgentCell,
    ErrorCell,
    ExecCell,
    FinalSeparatorCell,
    HookCell,
    McpToolCallCell,
    PatchHistoryCell,
    PlanUpdateCell,
    ProposedPlanCell,
    ReasoningCell,
    WarningCell,
    WebSearchCell,
)
from .state import TurnV2State

STREAMING_ELEMENT_ID = "streaming_content"
PROCESS_LOG_PANEL_TITLE = "Execution Log"


# ---- transcript rendering -------------------------------------------------


def render_transcript(state: TurnV2State) -> str:
    """将 transcript_cells + active_cell 渲染为 markdown 字符串。"""
    blocks: list[str] = []

    # 历史 cells（最近 12 条）
    for cell in state.transcript_cells[-12:]:
        rendered = _render_one_cell(cell, running=False, spinner_frame=state.spinner_frame)
        if rendered:
            blocks.append(rendered)

    # 当前 active_cell
    if state.active_cell is not None:
        rendered = _render_one_cell(state.active_cell, running=True, spinner_frame=state.spinner_frame)
        if rendered:
            blocks.append(rendered)

    # active_hook_cell
    if state.active_hook_cell is not None:
        rendered = _render_one_cell(state.active_hook_cell, running=True, spinner_frame=state.spinner_frame)
        if rendered:
            blocks.append(rendered)

    # reasoning buffer
    if state.reasoning_buffer.strip():
        blocks.append(f"💭 **Thinking...**\n\n{state.reasoning_buffer.strip()}")

    content = "\n\n".join(b for b in blocks if b).strip()

    # 如果没有任何内容，显示状态栏 + spinner
    if not content:
        header = state.status_header or "Working"
        spinner = SPINNER_FRAMES[state.spinner_frame % 3]
        content = f"{header} {spinner}"

    return content


def render_final_transcript(state: TurnV2State) -> str:
    """将工具执行相关的 transcript_cells 渲染为执行日志 markdown。

    排除 AgentMessageCell / AgentMarkdownCell（这些是最终回复，放 panel 外）。
    """
    from .cells import AgentMarkdownCell, AgentMessageCell

    blocks: list[str] = []
    for cell in state.transcript_cells:
        if isinstance(cell, (AgentMessageCell, AgentMarkdownCell)):
            continue
        rendered = _render_one_cell(cell, running=False, spinner_frame=0)
        if rendered:
            blocks.append(rendered)

    if state.reasoning_buffer.strip():
        blocks.append(f"💭 **Thought**\n\n{state.reasoning_buffer.strip()}")

    return "\n\n".join(b for b in blocks if b).strip()


def _extract_final_answer(state: TurnV2State) -> str:
    """从 transcript_cells 中提取最终 reply 文本。"""
    from .cells import AgentMarkdownCell

    for cell in reversed(state.transcript_cells):
        if isinstance(cell, AgentMarkdownCell):
            return cell.source.strip()
    # fallback: 从 stream_controller 的 raw_source 取
    raw = state.stream_controller.raw_source.strip()
    if raw:
        return raw
    return ""


def _render_one_cell(cell, *, running: bool, spinner_frame: int) -> str:
    if isinstance(cell, ExecCell):
        return render_exec_cell(cell, running=running, spinner_frame=spinner_frame)
    if isinstance(cell, McpToolCallCell):
        return render_mcp_tool_call_cell(cell, running=running, spinner_frame=spinner_frame)
    if isinstance(cell, PatchHistoryCell):
        return render_patch_history_cell(cell, running=running, spinner_frame=spinner_frame)
    if isinstance(cell, WebSearchCell):
        return render_web_search_cell(cell, running=running, spinner_frame=spinner_frame)
    if isinstance(cell, CollabAgentCell):
        return render_collab_agent_cell(cell, running=running, spinner_frame=spinner_frame)
    if isinstance(cell, AgentMessageCell):
        return render_agent_markdown_cell(AgentMarkdownCell(source=cell.source_line))
    if isinstance(cell, AgentMarkdownCell):
        return render_agent_markdown_cell(cell)
    if isinstance(cell, ReasoningCell):
        return render_reasoning_cell(cell)
    if isinstance(cell, HookCell):
        return render_hook_cell(cell, running=running, spinner_frame=spinner_frame)
    if isinstance(cell, PlanUpdateCell):
        return render_plan_update_cell(cell)
    if isinstance(cell, ProposedPlanCell):
        return render_proposed_plan_cell(cell)
    if isinstance(cell, WarningCell):
        return render_warning_cell(cell)
    if isinstance(cell, ErrorCell):
        return render_error_cell(cell)
    if isinstance(cell, FinalSeparatorCell):
        return render_final_separator_cell(cell)
    return ""


# ---- card JSON builders ---------------------------------------------------


def build_initial_card_json() -> dict:
    """初始空白 streaming card。"""
    return {
        "schema": "2.0",
        "config": {"streaming_mode": True},
        "body": {
            "elements": [
                {
                    "tag": "markdown",
                    "content": "",
                    "text_align": "left",
                    "text_size": "normal_v2",
                    "margin": "0px 0px 0px 0px",
                    "element_id": STREAMING_ELEMENT_ID,
                }
            ]
        },
    }


def build_streaming_card_json(state: TurnV2State) -> dict:
    """构建 streaming card JSON。"""
    content = render_transcript(state)
    return {
        "schema": "2.0",
        "config": {"streaming_mode": True},
        "body": {
            "elements": [
                {
                    "tag": "markdown",
                    "content": content,
                    "text_align": "left",
                    "text_size": "normal_v2",
                    "margin": "0px 0px 0px 0px",
                    "element_id": STREAMING_ELEMENT_ID,
                }
            ]
        },
    }


def build_final_card_json(state: TurnV2State, *, fallback_text: str = "") -> dict:
    """构建 final card JSON。

    - 执行日志放在 collapsible_panel 中
    - 最终 assistant 文本放在 panel 外
    """
    transcript = render_final_transcript(state)
    elements: list[dict] = []

    if transcript:
        elements.append({
            "tag": "collapsible_panel",
            "expanded": False,
            "header": {
                "title": {
                    "tag": "markdown",
                    "content": PROCESS_LOG_PANEL_TITLE,
                },
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
                    "content": transcript,
                    "text_size": "notation",
                }
            ],
        })

    # 最终 assistant 文本
    answer = _extract_final_answer(state) or fallback_text or "回复为空。"
    elements.append({"tag": "markdown", "content": answer})

    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True, "update_multi": True},
        "body": {"elements": elements},
    }

