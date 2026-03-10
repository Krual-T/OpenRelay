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
