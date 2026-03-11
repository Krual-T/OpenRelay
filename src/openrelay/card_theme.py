from __future__ import annotations

from typing import Any


CARD_CONFIG = {"wide_screen_mode": True, "enable_forward": True, "update_multi": True}
CARD_TEMPLATE_BY_TONE = {
    "info": "blue",
    "running": "blue",
    "success": "green",
    "error": "red",
    "cancelled": "grey",
}
CARD_LABEL_BY_TONE = {
    "info": "信息",
    "running": "进行中",
    "success": "已完成",
    "error": "失败",
    "cancelled": "已取消",
}
CARD_EMOJI_BY_TONE = {
    "info": "ℹ️",
    "running": "🟦",
    "success": "✅",
    "error": "❌",
    "cancelled": "⏹️",
}


def normalize_tone(tone: str | None) -> str:
    value = str(tone or "info").strip().lower()
    return value if value in CARD_TEMPLATE_BY_TONE else "info"


def header_template(tone: str | None) -> str:
    return CARD_TEMPLATE_BY_TONE[normalize_tone(tone)]


def status_label(tone: str | None) -> str:
    return CARD_LABEL_BY_TONE[normalize_tone(tone)]


def status_emoji(tone: str | None) -> str:
    return CARD_EMOJI_BY_TONE[normalize_tone(tone)]


def status_badge(tone: str | None) -> str:
    return f"`{status_label(tone)}`"


def build_card_shell(title: str, elements: list[dict[str, Any]], tone: str = "info") -> dict[str, Any]:
    return {
        "config": dict(CARD_CONFIG),
        "header": {
            "template": header_template(tone),
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": elements,
    }


def markdown_block(content: str) -> dict[str, Any]:
    return {"tag": "div", "text": {"tag": "lark_md", "content": str(content or "").strip()}}


def divider_block() -> dict[str, Any]:
    return {"tag": "hr"}


def build_code_panel(lines: list[object], *, language: str = "text") -> dict[str, Any] | None:
    normalized_lines = [str(line or "").strip() for line in lines if str(line or "").strip()]
    if not normalized_lines:
        return None
    return markdown_block(f"```{language}\n" + "\n".join(normalized_lines) + "\n```")


def build_fact_panel(items: list[tuple[str, object]]) -> dict[str, Any] | None:
    lines: list[str] = []
    for label, value in items:
        normalized_label = str(label or "").strip()
        normalized_value = str(value or "").replace("**", "").strip()
        normalized_value = " | ".join(part.strip() for part in normalized_value.splitlines() if part.strip())
        if not normalized_label or not normalized_value:
            continue
        lines.append(f"{normalized_label}：{normalized_value}")
    return build_code_panel(lines)


def build_note_bar(items: list[object]) -> dict[str, Any] | None:
    elements = [{"tag": "lark_md", "content": str(item).strip()} for item in items if str(item or "").strip()]
    if not elements:
        return None
    return {"tag": "note", "elements": elements}


def build_collapsible_panel(title: str, content: object, *, expanded: bool = False) -> dict[str, Any] | None:
    normalized_title = str(title or "").strip()
    normalized_content = str(content or "").strip()
    if not normalized_title or not normalized_content:
        return None
    return {
        "tag": "collapsible_panel",
        "expanded": expanded,
        "header": {
            "title": {"tag": "markdown", "content": normalized_title},
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
                "content": normalized_content,
                "text_size": "notation",
            }
        ],
    }


def build_status_hero(
    title: str,
    *,
    tone: str,
    summary: str = "",
    facts: list[tuple[str, object]] | None = None,
    notes: list[object] | None = None,
) -> list[dict[str, Any]]:
    lines = [build_status_heading(tone, title)]
    if str(summary or "").strip():
        lines.append(f"> {str(summary).strip()}")
    elements = [markdown_block("\n".join(lines))]
    facts_block = build_fact_panel(facts or [])
    if facts_block is not None:
        elements.append(facts_block)
    note_block = build_note_bar(notes or [])
    if note_block is not None:
        elements.append(note_block)
    return elements


def build_section_block(title: str, lines: list[object], *, emoji: str = "", summary: str = "") -> dict[str, Any]:
    heading = f"**{emoji} {title}**" if emoji else f"**{title}**"
    content_lines = [heading]
    if str(summary or "").strip():
        content_lines.append(f"> {str(summary).strip()}")
    for line in lines:
        normalized = str(line or "").strip()
        if normalized:
            content_lines.append(normalized)
    return markdown_block("\n".join(content_lines))


def infer_final_tone(text: object) -> str:
    value = str(text or "").strip()
    if not value:
        return "success"
    lowered = value.lower()
    if value.startswith("处理失败：") or value.startswith("失败：") or "traceback" in lowered:
        return "error"
    if value.startswith("已停止") or value.startswith("已取消") or "interrupted" in lowered:
        return "cancelled"
    return "success"


def build_status_heading(tone: str, title: str, *, prefix: str = "") -> str:
    parts = [part for part in [prefix.strip(), status_emoji(tone), status_badge(tone), f"**{title.strip()}**" if title.strip() else ""] if part]
    return " ".join(parts).strip()
