from __future__ import annotations

from typing import Any

from openrelay.feishu.cards import build_button, build_card_shell, build_section_block, build_status_hero, divider_block
from openrelay.core import AppConfig, SessionRecord, format_release_channel, infer_release_channel
from openrelay.session import SessionUX
from openrelay.storage import StateStore


class HelpRenderer:
    def __init__(self, config: AppConfig, store: StateStore, session_ux: SessionUX):
        self.config = config
        self.store = store
        self.session_ux = session_ux

    def build_text(self, session: SessionRecord, available_backends: list[str]) -> str:
        message_count = len(self.store.list_messages(session.session_id))
        context_lines = self.session_ux.build_context_lines(session, limit=2)
        context_preview = self.session_ux.build_context_preview(session, limit=2)
        lines = [
            "OpenRelay 帮助",
            "",
            "当前状态：",
            f"- 会话：{session.label or '未命名会话'} ({session.session_id})",
            f"- 会话阶段：{self.describe_session_phase(session, message_count)}",
            f"- 通道：{format_release_channel(infer_release_channel(self.config, session))}",
            f"- 目录：{self.session_ux.format_cwd(session.cwd, session)}",
            f"- 后端：{session.backend}",
            f"- 模型：{self.session_ux.effective_model(session)}",
            f"- sandbox：{session.safety_mode}",
            f"- 后端线程：{session.native_session_id or 'pending（直接发消息就会创建）'}",
            f"- 上下文占用：{self.session_ux.format_context_usage(session)}",
            f"- 本地消息数：{message_count}",
            f"- 最近关注：{context_preview or '还没有可总结的本地上下文'}",
            "",
            "一句话判断：",
            f"- {self.build_now_summary(session, message_count)}",
        ]
        context_note = self.build_context_note(session)
        if context_note:
            lines.append(context_note)
        lines.extend(
            [
                "",
                "你现在最该做什么：",
                *self.build_priority_actions(session, message_count),
                "",
                "下一条消息可以直接这样发：",
                *self.build_prompt_examples(session, message_count),
                "",
                "什么时候该用命令：",
                *self.build_command_guide(session, available_backends),
                "",
                "最近上下文：",
                *context_lines,
                "",
                "提示：如果目标没变，别先发命令，直接补充任务、报错、文件路径，或明确让它继续下一步。",
            ]
        )
        return "\n".join(lines)

    def build_card(self, session: SessionRecord, available_backends: list[str], action_context: dict[str, str] | None = None) -> dict[str, Any]:
        message_count = len(self.store.list_messages(session.session_id))
        context_preview = self.session_ux.build_context_preview(session, limit=2)
        actions_context = action_context or {}
        elements: list[dict[str, Any]] = [
            *build_status_hero(
                "当前状态",
                tone="info",
                summary=self.build_now_summary(session, message_count),
                facts=[
                    ("会话", f"{session.label or '未命名会话'}\n`{session.session_id}`"),
                    ("阶段", self.describe_session_phase(session, message_count)),
                    ("通道", f"`{format_release_channel(infer_release_channel(self.config, session))}`"),
                    ("目录", f"`{self.session_ux.format_cwd(session.cwd, session)}`"),
                    ("后端 / 模型", f"`{session.backend}` · `{self.session_ux.effective_model(session)}`"),
                    ("Sandbox / 后端线程", f"`{session.safety_mode}` · `{session.native_session_id or 'pending'}`"),
                    ("上下文 / 本地消息", f"`{self.session_ux.format_context_usage(session)}` · `{message_count}`"),
                ],
                notes=[f"最近关注：{context_preview or '还没有可总结的本地上下文'}"],
            )
        ]
        context_note = self.build_context_note(session)
        if context_note:
            elements.append(build_section_block("上下文提醒", [context_note], emoji="⚠️"))
        elements.extend(
            [
                divider_block(),
                build_section_block("你现在最该做什么", self.build_priority_actions(session, message_count), emoji="🎯"),
                divider_block(),
                build_section_block("下一条消息可以直接这样发", self.build_prompt_examples(session, message_count), emoji="✍️"),
                divider_block(),
                build_section_block(
                    "什么时候该用命令",
                    [
                        *self.build_command_guide(session, available_backends),
                        "",
                        "> 点击下面按钮即可直接执行对应命令；如果任务没变，直接发消息通常更快。",
                    ],
                    emoji="🧭",
                ),
            ]
        )
        for group in self.build_command_button_groups(available_backends, actions_context):
            elements.append({"tag": "action", "actions": group})
        return build_card_shell("openrelay help", elements, tone="info")

    def describe_session_phase(self, session: SessionRecord, message_count: int) -> str:
        if message_count == 0 and session.native_session_id:
            return "仅后端线程已连接（可继续发消息，但本地暂未缓存上下文）"
        if message_count == 0:
            return "未开始（还没发第一条真实需求）"
        if session.native_session_id:
            return "进行中（继续发消息会沿用当前后端线程）"
        return "待启动（已有本地上下文，下一条真实消息会创建后端线程）"

    def build_now_summary(self, session: SessionRecord, message_count: int) -> str:
        if message_count == 0 and session.native_session_id:
            return "这是一个已连接后端线程但本地上下文为空的会话；直接发消息会继续当前后端线程。"
        if message_count == 0:
            return "这是一个空会话；最有效的动作通常是直接发完整任务，而不是先试很多命令。"
        if session.native_session_id:
            return "这是一个进行中的会话；如果任务没变，直接补充信息最快。"
        return "这是一个已有本地上下文但尚未重新连上后端执行的会话；下一条真实消息会自动接上。"

    def build_context_note(self, session: SessionRecord) -> str | None:
        usage_ratio = self.context_usage_ratio(session)
        if usage_ratio is None:
            return None
        if usage_ratio >= 0.85:
            return "- 上下文提醒：当前上下文已经接近窗口上限；如果要开新任务，优先 /new，别继续混在这个会话里。"
        if usage_ratio >= 0.65:
            return "- 上下文提醒：当前上下文已经不短；如果话题要明显切换，建议先 /new 隔离。"
        return None

    def context_usage_ratio(self, session: SessionRecord) -> float | None:
        usage = session.last_usage if isinstance(session.last_usage, dict) else {}
        total_tokens = usage.get("total_tokens")
        model_context_window = usage.get("model_context_window")
        try:
            total_value = int(total_tokens)
            window_value = int(model_context_window)
        except (TypeError, ValueError):
            return None
        if window_value <= 0:
            return None
        return total_value / window_value

    def build_priority_actions(self, session: SessionRecord, message_count: int) -> list[str]:
        if message_count == 0 and session.native_session_id:
            return [
                "- 想延续当前 backend session：直接发消息，不需要先补命令。",
                "- 想改成新任务：先 /new <label>，再发新需求，避免旧上下文干扰。",
                "- 想先确认目录、模型、通道和最近上下文，发 /status。",
            ]
        if message_count == 0:
            return [
                "- 先把目标说完整：要改什么、在哪个目录、是否要直接改代码。",
                "- 有明确目录就先 /cwd <path>；没有就直接发任务，别把时间花在命令上。",
                "- 如果这是稳定版本排障，用 /main；如果是实验性修复，用 /develop。",
            ]
        if session.native_session_id:
            return [
                "- 如果还是同一件事，直接追加信息：目标、报错、文件路径、验收标准。",
                "- 当前回复还没结束时，继续发消息会自动排到下一轮；连续补充会合并处理。",
                "- 如果你想让它立刻推进，直接说“继续，先做下一步并汇报改动”。",
                "- 如果任务已经变了，先 /new <label>，不要把新需求继续塞进当前会话。",
            ]
        return [
            "- 直接再发一条真实消息，系统会基于当前本地上下文重新接上执行。",
            "- 如果现在其实是新任务，先 /new <label> 隔离上下文。",
            "- 如果你要回到更早的某次对话，先 /resume list 再恢复。",
        ]

    def build_prompt_examples(self, session: SessionRecord, message_count: int) -> list[str]:
        if message_count == 0 and session.native_session_id:
            return [
                '- “继续刚才那个任务，先回顾当前进度，再直接往下做。”',
                '- “不要开新话题，基于当前会话继续修这个问题：<描述>。”',
                '- “先告诉我你准备怎么继续，然后直接开始。”',
                '- “如果你判断这已经是新任务，提醒我先 /new，再继续。”',
            ]
        if message_count == 0:
            return [
                '- “先快速读一下这个仓库，告诉我入口、运行方式和关键目录。”',
                '- “定位这个报错的根因：<贴报错>; 先解释判断，再直接修复。”',
                '- “在 <path> 下实现 <需求>；先列计划，再按最小改动完成。”',
                '- “先不要改代码，帮我梳理实现方案、风险和验收点。”',
            ]
        if session.native_session_id:
            return [
                '- “继续刚才的任务，下一步先检查 <file/path>，然后直接改。”',
                '- “这个报错还在：<贴报错>; 结合当前上下文继续排查。”',
                '- “先记住这条补充，等你输出完上一条后继续处理：<补充信息>。”',
                '- “基于现在的进度继续，不要重来；做完告诉我改了哪些文件。”',
                '- “先别写代码，帮我总结当前进度、阻塞点和下一步。”',
            ]
        return [
            '- “基于当前上下文继续，先总结你理解的现状，再直接往下做。”',
            '- “把最近这个任务接上，先检查 <file/path>，然后继续实现。”',
            '- “如果当前上下文不足以继续，请明确告诉我缺什么信息。”',
            '- “先帮我整理当前上下文里的目标、已完成项和待做项。”',
        ]

    def build_command_guide(self, session: SessionRecord, available_backends: list[str]) -> list[str]:
        shortcut_entries = self.session_ux.build_directory_shortcut_entries(session)
        lines = [
            "- 同一任务继续干：通常不用命令，直接发消息。",
            "- 当前回复还在跑时，继续发消息会进入下一轮；连续补充会自动合并。",
            "- 私聊顶层直接发新消息：默认会开新的 Codex 会话；想回旧会话时再用 /resume。",
            "- 开新任务或切话题：/new <label>；回旧 backend session：/resume list、/resume latest。",
            "- `/new` 和 `/resume` 只允许在私聊顶层使用；子 thread 会固定绑定当前 Codex 会话。",
            "- `/resume` 只恢复本地 session_id，不直接暴露原生 thread 历史。",
            "- 换执行位置：/cwd <path> 切目录；/main 回稳定工作区；/develop 进修复工作区。",
            "- 快捷目录：/shortcut add <name> <path> [all|main|develop]、/shortcut list、/shortcut cd <name>。",
            "- 看现场：/status 看会话、目录、最近上下文；/usage 看 token 和 context_usage。",
            "- 面板导航：/panel 打开总入口；/panel sessions、/panel directories、/panel commands、/panel status 进入对应结果面；从卡片按钮切换时会优先留在同一张卡。",
            "- 控制运行：/stop 停止生成；/clear 清空当前上下文；需要更完整说明时再发 /help。",
            "- 环境与维护：/model 切模型；/sandbox 切执行模式；/ping 连通性检查；/restart 管理员用。",
        ]
        if shortcut_entries:
            lines.insert(4, "- 常用目录：如果 `/panel` 已显示快捷目录，优先直接点按钮；这些入口会稳定复用 `/cwd` 主路径。")
        if len(available_backends) > 1:
            lines.append(f"- 切后端：/backend [list|{'|'.join(available_backends)}]。")
        return lines

    def build_command_button_groups(self, available_backends: list[str], action_context: dict[str, str]) -> list[list[dict[str, Any]]]:
        groups: list[list[tuple[str, str, str]]] = [
            [("状态", "/status", "primary"), ("用量", "/usage", "default"), ("面板", "/panel", "default")],
            [("新会话", "/new", "primary"), ("会话列表", "/resume list", "default"), ("清空上下文", "/clear", "default")],
            [("当前目录", "/cwd", "default"), ("切到 main", "/main", "default"), ("切到 develop", "/develop", "default")],
            [("模型", "/model", "default"), ("Sandbox", "/sandbox", "default"), ("停止", "/stop", "default")],
        ]
        if len(available_backends) > 1:
            groups[-1].insert(2, ("后端", "/backend list", "default"))
        return [[build_button(label, command, button_type, action_context) for label, command, button_type in group] for group in groups]
