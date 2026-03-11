from __future__ import annotations

import re
from typing import Any


STREAMING_ELEMENT_ID = "streaming_content"
LOADING_ELEMENT_ID = "loading_icon"
DEFAULT_THINKING_TEXT = "思考中..."
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


def strip_markdown_for_summary(text: object, max_length: int = 120) -> str:
    summary = str(text or "").replace("*", "").replace("_", "").replace("`", "").replace("#", "").replace(">", "")
    summary = summary.replace("[", "").replace("]", "").replace("(", "").replace(")", "").replace("~", "")
    summary = " ".join(summary.split()).strip()
    if len(summary) <= max_length:
        return summary
    return summary[: max_length - 3] + "..."


def build_thinking_card_json() -> dict[str, Any]:
    return {
        "schema": "2.0",
        "config": {
            "streaming_mode": True,
            "summary": {"content": DEFAULT_THINKING_TEXT},
        },
        "body": {
            "elements": [
                {
                    "tag": "markdown",
                    "content": "",
                    "text_align": "left",
                    "text_size": "normal_v2",
                    "margin": "0px 0px 0px 0px",
                    "element_id": STREAMING_ELEMENT_ID,
                },
                {
                    "tag": "markdown",
                    "content": " ",
                    "icon": {
                        "tag": "custom_icon",
                        "img_key": LOADING_ICON_IMAGE_KEY,
                        "size": "16px 16px",
                    },
                    "element_id": LOADING_ELEMENT_ID,
                },
            ]
        },
    }


def build_streaming_content(live_state: dict[str, Any] | None = None) -> str:
    live_state = live_state or {}
    partial_text = str(live_state.get("partial_text") or "").strip()
    if partial_text:
        partial_reasoning, partial_answer = split_reasoning_text(partial_text)
        answer = partial_answer or strip_reasoning_tags(partial_text)
        if answer:
            return optimize_markdown_style(answer)
        if partial_reasoning:
            return f"💭 **Thinking...**\n\n{partial_reasoning}"
    reasoning_text = str(live_state.get("reasoning_text") or live_state.get("last_reasoning") or "").strip()
    if reasoning_text:
        return f"💭 **Thinking...**\n\n{reasoning_text}"
    return ""


def build_complete_card(
    text: object,
    *,
    panel_text: object = "",
    panel_title: object = "🧾 中间过程",
) -> dict[str, Any]:
    raw_text = str(text or "").strip() or "回复为空。"
    extracted_reasoning, extracted_answer = split_reasoning_text(raw_text)
    final_panel_text = str(panel_text or "").strip() or extracted_reasoning
    final_answer = extracted_answer or raw_text

    elements: list[dict[str, Any]] = []
    if final_panel_text:
        elements.append(
            {
                "tag": "collapsible_panel",
                "expanded": False,
                "header": {
                    "title": {"tag": "markdown", "content": str(panel_title or "🧾 中间过程").strip()},
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
                        "content": final_panel_text,
                        "text_size": "notation",
                    }
                ],
            }
        )

    elements.append({"tag": "markdown", "content": optimize_markdown_style(final_answer)})

    summary = strip_markdown_for_summary(final_answer)
    config: dict[str, Any] = {"wide_screen_mode": True, "update_multi": True}
    if summary:
        config["summary"] = {"content": summary}
    return {
        "schema": "2.0",
        "config": config,
        "body": {"elements": elements},
    }
