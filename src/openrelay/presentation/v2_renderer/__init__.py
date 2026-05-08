"""Codex v2 渲染层。

直接消费 ServerNotification / ServerRequest，按官方 Codex TUI ChatWidget
模式渲染为飞书 CardKit JSON。
"""

from .renderer import TurnV2Renderer

__all__ = ["TurnV2Renderer"]
