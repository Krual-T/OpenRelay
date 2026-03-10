from __future__ import annotations

from dataclasses import dataclass, field, replace

from openrelay.models import IncomingMessage


MERGED_FOLLOW_UP_INTRO = "用户在上一条回复完成前连续补充了下面这些信息，请合并理解后继续当前任务："


@dataclass(slots=True)
class QueuedFollowUp:
    anchor_message: IncomingMessage
    prompts: list[str] = field(default_factory=list)
    local_image_paths: list[str] = field(default_factory=list)

    @classmethod
    def from_message(cls, message: IncomingMessage) -> QueuedFollowUp:
        return cls(
            anchor_message=message,
            prompts=[message.text],
            local_image_paths=list(message.local_image_paths),
        )

    @property
    def message_count(self) -> int:
        return len(self.prompts)

    def merge(self, message: IncomingMessage) -> None:
        self.anchor_message = message
        self.prompts.append(message.text)
        self.local_image_paths.extend(message.local_image_paths)

    def acknowledgement_text(self) -> str:
        if self.message_count == 1:
            return "已收到补充，会在当前回复结束后自动继续；后续新补充会合并到下一轮。"
        return f"已收到补充，当前累计 {self.message_count} 条；当前回复结束后会合并成下一轮继续。"

    def to_message(self) -> IncomingMessage:
        prompt = self.prompts[0] if self.message_count == 1 else self._build_merged_prompt()
        return replace(self.anchor_message, text=prompt, local_image_paths=tuple(self.local_image_paths))

    def _build_merged_prompt(self) -> str:
        parts = [MERGED_FOLLOW_UP_INTRO]
        for index, prompt in enumerate(self.prompts, start=1):
            parts.append(f"补充消息 {index}：\n{prompt}")
        return "\n\n".join(parts)
