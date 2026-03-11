from __future__ import annotations

from typing import Any

from openrelay.card_theme import build_status_heading, status_emoji


def normalize_inline(text: object) -> str:
    return " ".join(str(text or "").split()).strip()



def shorten(text: object, max_length: int = 96) -> str:
    value = normalize_inline(text)
    if len(value) <= max_length:
        return value
    return f"{value[:max_length - 3]}..."



def extract_reasoning_title(text: object) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    lines = value.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("**") and "**" in stripped[2:]:
            return shorten(stripped.strip("*"), 80)
        if stripped:
            return shorten(stripped, 80)
    return shorten(value, 80)



def first_non_empty_line(text: object) -> str:
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""



def dedupe_strings(values: list[object]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = normalize_inline(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result



def resolve_spinner_dots(state: dict[str, Any]) -> str:
    frames = [["·", "•", "●"], ["●", "·", "•"], ["•", "●", "·"]]
    index = abs(int(state.get("spinner_frame", 0) or 0)) % len(frames)
    return " ".join(frames[index])



def resolve_semantic_emoji(text: object = "") -> str:
    value = normalize_inline(text)
    if not value:
        return "⏳"
    if "启动" in value or "start" in value.lower():
        return "🚀"
    if "连接" in value or "thread" in value.lower() or "会话已连接" in value:
        return "🔗"
    if "准备" in value:
        return "🧭"
    if any(token in value for token in ["执行", "命令", "shell", "bash"]):
        return "💻"
    if any(token in value for token in ["输出", "生成回复", "回复", "assistant"]):
        return "✍️"
    if any(token in value for token in ["分析", "计划", "reason"]):
        return "🧠"
    if any(token in value for token in ["整理结果", "结果", "收尾"]):
        return "📦"
    if any(token in value for token in ["完成", "done", "success"]):
        return "✅"
    return "⏳"



def format_elapsed(started_at: object, now_ts: float | None = None) -> str:
    import time

    try:
        if isinstance(started_at, (int, float)):
            start = float(started_at)
        else:
            from datetime import datetime

            start = datetime.fromisoformat(str(started_at)).timestamp()
    except Exception:
        return ""
    now_value = now_ts if now_ts is not None else time.time()
    total_seconds = max(0, int(now_value - start))
    if total_seconds < 60:
        return f"{total_seconds}s"
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {seconds:02d}s"



def render_markdown_panel(lines: list[object]) -> str:
    normalized_lines: list[str] = []
    for line in lines:
        normalized = str(line or "").strip()
        if not normalized:
            continue
        if normalized.startswith(">"):
            normalized = normalized[1:].lstrip()
        if normalized:
            normalized_lines.append(normalized)
    if not normalized_lines:
        return ""
    return "```text\n" + "\n".join(normalized_lines) + "\n```"


def build_reasoning_body_text(text: object) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    return f"💭 **Thinking...**\n\n{normalized}"


def build_activity_summary(activity: dict[str, Any] | None = None) -> str:
    activity = activity or {}
    lines: list[str] = []
    hidden = 0
    reasoning_titles = dedupe_strings([extract_reasoning_title(entry.get("text") if isinstance(entry, dict) else entry) for entry in activity.get("reasoning", [])])
    for title in reasoning_titles[:2]:
        lines.append(f"- 推理：{title}")
    hidden += max(0, len(reasoning_titles) - 2)
    statuses = dedupe_strings(activity.get("statuses", []))
    for status in statuses[:2]:
        lines.append(f"- 状态：{shorten(status, 90)}")
    hidden += max(0, len(statuses) - 2)
    commands = activity.get("commands") or []
    if isinstance(commands, list):
        for command in commands[:3]:
            if not isinstance(command, dict):
                continue
            base = f"- 命令：`{shorten(command.get('command', ''), 72)}`"
            exit_code = command.get("exitCode")
            if exit_code is not None:
                base += f" · exit {exit_code}"
            output_preview = shorten(first_non_empty_line(command.get("outputPreview") or command.get("output") or ""), 72)
            lines.append(f"{base}\n  - 输出：`{output_preview}`" if output_preview else base)
        hidden += max(0, len(commands) - 3)
    usage = activity.get("usage") if isinstance(activity.get("usage"), dict) else {}
    input_tokens = usage.get("input_tokens") or usage.get("inputTokens")
    output_tokens = usage.get("output_tokens") or usage.get("outputTokens")
    cached_tokens = usage.get("cached_input_tokens") or usage.get("cachedInputTokens")
    if input_tokens or output_tokens or cached_tokens:
        parts: list[str] = []
        if input_tokens:
            parts.append(f"in {input_tokens}")
        if cached_tokens:
            parts.append(f"cache {cached_tokens}")
        if output_tokens:
            parts.append(f"out {output_tokens}")
        lines.append(f"- 用量：{' · '.join(parts)}")
    if hidden > 0:
        lines.append(f"- 其余 {hidden} 条活动已折叠")
    return "\n".join(lines).strip()



def build_live_status_view(state: dict[str, Any] | None = None) -> dict[str, object]:
    state = state or {}
    heading = shorten(state.get("heading") or state.get("status") or "正在处理中", 90)
    spinner = resolve_spinner_dots(state)
    semantic_source = f"{state.get('heading', '')} {state.get('status', '')}"
    heading_emoji = resolve_semantic_emoji(semantic_source)
    header_lines = [build_status_heading("running", heading, prefix=f"{spinner} {heading_emoji}")]
    detail_lines: list[str] = []

    current_text = ""
    if state.get("current_command"):
        current_text = f"执行 `{shorten(state['current_command'], 72)}`"
    elif any(token in semantic_source for token in ["分析", "计划", "reason"]) and state.get("last_reasoning"):
        current_text = f"分析 {extract_reasoning_title(state['last_reasoning'])}"
    elif state.get("status"):
        current_text = shorten(state["status"], 90)
    elif heading:
        current_text = heading
    if current_text:
        detail_lines.append(f"> {status_emoji('running')} 当前：{current_text}")

    reasoning_title = extract_reasoning_title(state.get("last_reasoning")) if state.get("last_reasoning") else ""
    if reasoning_title and not any(token in current_text for token in ["分析", "计划", "reason"]):
        detail_lines.append(f"> 🧠 目的：{reasoning_title}")
    else:
        last_command = state.get("last_command") if isinstance(state.get("last_command"), dict) else {}
        if last_command.get("command") and isinstance(last_command.get("exitCode"), int) and int(last_command.get("exitCode")) != 0:
            detail_lines.append(f"> ⚠️ 最近结果：`{shorten(last_command.get('command', ''), 56)}` · exit {last_command.get('exitCode')}")

    elapsed = format_elapsed(state.get("started_at") or state.get("startedAt"))
    if elapsed:
        detail_lines.append(f"> ⏱️ 已处理：{elapsed}")

    body_text = str(state.get("partial_text") or "").strip()
    if not body_text:
        body_text = build_reasoning_body_text(state.get("reasoning_text"))
    return {"header_lines": header_lines, "detail_lines": detail_lines, "body_text": body_text}



def render_reply_markdown(reply: object) -> str:
    if isinstance(reply, str):
        return reply.strip()
    if hasattr(reply, "text"):
        return str(getattr(reply, "text") or "").strip()
    return str(reply or "").strip()



def render_live_status_markdown(state: dict[str, Any] | None = None) -> str:
    view = build_live_status_view(state)
    lines = list(view["header_lines"])
    detail_panel = render_markdown_panel(list(view["detail_lines"]))
    if detail_panel:
        lines.extend(["", detail_panel])
    body_text = str(view["body_text"] or "")
    if body_text:
        lines.extend(["", "---", body_text])
    return "\n".join(lines).strip()


def render_live_status_sections(state: dict[str, Any] | None = None) -> dict[str, str]:
    view = build_live_status_view(state)
    return {
        "header": "\n".join(view["header_lines"]).strip(),
        "details": render_markdown_panel(list(view["detail_lines"])),
        "body": str(view["body_text"] or ""),
    }
