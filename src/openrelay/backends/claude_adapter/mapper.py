from __future__ import annotations

import json
from typing import Any

from openrelay.core import BackendReply


class ClaudeResponseMapper:
    def parse(self, payload_text: str) -> BackendReply:
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            return BackendReply(text=payload_text)

        if not isinstance(payload, dict):
            return BackendReply(text=payload_text)

        text = self._extract_text(payload)
        session_id = str(payload.get("session_id") or payload.get("sessionId") or "")
        return BackendReply(text=text or payload_text, native_session_id=session_id, metadata=payload)

    def _extract_text(self, payload: dict[str, Any]) -> str:
        if isinstance(payload.get("result"), str) and payload["result"].strip():
            return payload["result"].strip()
        if isinstance(payload.get("text"), str) and payload["text"].strip():
            return payload["text"].strip()
        message = payload.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip():
                        parts.append(item["text"].strip())
                if parts:
                    return "\n".join(parts).strip()
        return ""
