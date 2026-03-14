from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Awaitable, Callable

from openrelay.card_actions import build_button
from openrelay.card_theme import build_card_shell, build_section_block, build_status_hero, divider_block
from openrelay.models import IncomingMessage

from .formatting import (
    chunk_actions,
    format_command_actions,
    format_permissions,
    normalize_decision_text,
    normalize_text,
    shorten,
    strip_code_fences,
)
from .models import INTERACTION_COMMAND_PREFIX, InteractionResolution, PendingInteraction, build_interaction_command


class RunInteractionController:
    def __init__(
        self,
        messenger: Any,
        *,
        chat_id: str,
        root_id: str,
        action_context: dict[str, str],
        reply_target_getter: Callable[[], str],
        emit_progress: Callable[[dict[str, Any]], Awaitable[None]],
        send_text: Callable[[str], Awaitable[None]],
        cancel_event: asyncio.Event | None,
    ) -> None:
        self.messenger = messenger
        self.chat_id = chat_id
        self.root_id = root_id
        self.action_context = action_context
        self.reply_target_getter = reply_target_getter
        self.emit_progress = emit_progress
        self.send_text = send_text
        self.cancel_event = cancel_event
        self.pending: PendingInteraction | None = None
        self._request_lock = asyncio.Lock()

    def has_pending_interaction(self) -> bool:
        return self.pending is not None

    async def shutdown(self) -> None:
        pending = self.pending
        self.pending = None
        if pending is not None and not pending.future.done():
            pending.future.set_result(pending.abort_resolution)

    async def request(self, method: str, params: dict[str, object]) -> dict[str, object]:
        async with self._request_lock:
            if method == "item/commandExecution/requestApproval":
                return await self._request_command_approval(params)
            if method == "item/fileChange/requestApproval":
                return await self._request_file_change_approval(params)
            if method == "item/permissions/requestApproval":
                return await self._request_permissions_approval(params)
            if method == "item/tool/requestUserInput":
                return await self._request_tool_user_input(params)
            if method == "mcpServer/elicitation/request":
                return await self._request_mcp_elicitation(params)
            raise NotImplementedError(method)

    async def try_handle_message(self, message: IncomingMessage) -> bool:
        pending = self.pending
        if pending is None:
            return False
        text = str(message.text or "").strip()
        if not text:
            await self.send_text(pending.prompt_text)
            return True
        if text.lower().startswith("/stop"):
            return False
        if text.startswith(INTERACTION_COMMAND_PREFIX):
            return await self._handle_command_reply(message, pending, text)
        if text.startswith("/"):
            await self.send_text(pending.prompt_text)
            return True
        if pending.text_handler is None:
            await self.send_text(pending.prompt_text)
            return True
        resolution = pending.text_handler(text)
        if resolution is None:
            await self.send_text(pending.prompt_text)
            return True
        if not pending.future.done():
            pending.future.set_result(resolution)
        return True

    async def _handle_command_reply(self, message: IncomingMessage, pending: PendingInteraction, text: str) -> bool:
        tokens = text.split(maxsplit=2)
        if len(tokens) < 3:
            await self.send_text(pending.prompt_text)
            return True
        interaction_id = tokens[1].strip()
        action = tokens[2].strip()
        if interaction_id != pending.interaction_id:
            await self.send_text(pending.prompt_text)
            return True
        resolution = (pending.command_resolutions or {}).get(action)
        if resolution is None:
            await self.send_text(pending.prompt_text)
            return True
        if not pending.future.done():
            pending.future.set_result(resolution)
        await self._update_interaction_card(message, pending, resolution)
        return True

    async def _await_pending(self, pending: PendingInteraction) -> InteractionResolution:
        self.pending = pending
        await self.emit_progress(
            {
                "type": "interaction.requested",
                "interaction": {
                    "id": pending.interaction_id,
                    "kind": pending.kind,
                    "title": pending.title,
                    "detail": pending.detail,
                },
            }
        )
        try:
            await self._send_interaction_card(pending)
            if self.cancel_event is None:
                resolution = await pending.future
            else:
                cancel_task = asyncio.create_task(self.cancel_event.wait())
                try:
                    done, _ = await asyncio.wait({pending.future, cancel_task}, return_when=asyncio.FIRST_COMPLETED)
                    if pending.future in done:
                        resolution = await pending.future
                    else:
                        resolution = pending.abort_resolution
                finally:
                    cancel_task.cancel()
            await self.emit_progress(
                {
                    "type": "interaction.resolved",
                    "interaction": {
                        "id": pending.interaction_id,
                        "kind": pending.kind,
                        "title": pending.title,
                        "state": resolution.state,
                        "detail": resolution.detail or resolution.label,
                    },
                }
            )
            return resolution
        finally:
            if self.pending is pending:
                self.pending = None

    async def _send_interaction_card(self, pending: PendingInteraction) -> None:
        await self.messenger.send_interactive_card(
            self.chat_id,
            self._build_interaction_card(pending),
            reply_to_message_id=self.reply_target_getter(),
            root_id=self.root_id,
        )

    async def _update_interaction_card(
        self,
        message: IncomingMessage,
        pending: PendingInteraction,
        resolution: InteractionResolution,
    ) -> None:
        update_message_id = str(message.reply_to_message_id or "").strip()
        if not update_message_id:
            return
        await self.messenger.send_interactive_card(
            self.chat_id,
            self._build_resolved_card(pending, resolution),
            update_message_id=update_message_id,
            root_id=self.root_id,
        )

    def _build_interaction_card(self, pending: PendingInteraction) -> dict[str, Any]:
        elements: list[dict[str, Any]] = [
            *build_status_hero(
                pending.title,
                tone="running",
                summary="Codex is waiting for your decision before it can continue.",
            ),
        ]
        if pending.detail:
            elements.extend([divider_block(), build_section_block("Request Details", pending.detail.splitlines(), emoji="🧾")])
        elements.extend([divider_block(), build_section_block("How To Reply", [pending.prompt_text], emoji="🧭")])
        actions = self._build_actions(pending)
        if actions:
            elements.append(divider_block())
            elements.append(build_section_block("Available Actions", ["Use the buttons below or reply in thread when text input is allowed."], emoji="🎛️"))
            for row in actions:
                elements.append({"tag": "action", "actions": row})
        return build_card_shell("openrelay interaction", elements, tone="running")

    def _build_resolved_card(self, pending: PendingInteraction, resolution: InteractionResolution) -> dict[str, Any]:
        tone = "success"
        if resolution.state in {"cancelled", "canceled"}:
            tone = "cancelled"
        elif resolution.state in {"failed", "error"}:
            tone = "error"
        elements = build_status_hero(
            pending.title,
            tone=tone,
            summary=resolution.label,
            notes=[resolution.detail or pending.detail] if (resolution.detail or pending.detail) else [],
        )
        return build_card_shell("openrelay interaction", elements, tone=tone)

    def _build_actions(self, pending: PendingInteraction) -> list[list[dict[str, Any]]]:
        actions: list[dict[str, Any]] = []
        for action, resolution in (pending.command_resolutions or {}).items():
            button_type = "default"
            if action.startswith("accept") or action.startswith("choice") or "accept" in action:
                button_type = "primary"
            if resolution.state in {"cancelled", "canceled"}:
                button_type = "default"
            actions.append(
                build_button(
                    resolution.label,
                    build_interaction_command(pending.interaction_id, action),
                    button_type,
                    self.action_context,
                )
            )
        return chunk_actions(actions)

    async def _request_command_approval(self, params: dict[str, object]) -> dict[str, object]:
        command = shorten(params.get("command") or "unknown command", 240)
        cwd = normalize_text(params.get("cwd"))
        reason = normalize_text(params.get("reason"))
        detail_lines = [f"Command: `{command}`"]
        if cwd:
            detail_lines.append(f"CWD: `{cwd}`")
        detail_lines.extend(format_command_actions(params.get("commandActions")))
        if reason:
            detail_lines.append(f"Reason: {reason}")
        pending = PendingInteraction(
            interaction_id=uuid.uuid4().hex[:12],
            kind="command_approval",
            title="Command Approval Required",
            detail="\n".join(detail_lines),
            prompt_text="Choose one of the approval buttons, or reply with: accept / session / decline / cancel.",
            future=asyncio.get_running_loop().create_future(),
            abort_resolution=InteractionResolution({"decision": "cancel"}, "Cancelled", state="cancelled"),
            text_handler=self._decision_text_handler(
                {
                    "accept": InteractionResolution({"decision": "accept"}, "Accept once"),
                    "acceptForSession": InteractionResolution({"decision": "acceptForSession"}, "Accept for session"),
                    "decline": InteractionResolution({"decision": "decline"}, "Decline", state="cancelled"),
                    "cancel": InteractionResolution({"decision": "cancel"}, "Cancel turn", state="cancelled"),
                }
            ),
            command_resolutions={
                "accept": InteractionResolution({"decision": "accept"}, "Allow once"),
                "accept_session": InteractionResolution({"decision": "acceptForSession"}, "Allow for session"),
                "decline": InteractionResolution({"decision": "decline"}, "Decline", state="cancelled"),
                "cancel": InteractionResolution({"decision": "cancel"}, "Cancel turn", state="cancelled"),
            },
        )
        return (await self._await_pending(pending)).response

    async def _request_file_change_approval(self, params: dict[str, object]) -> dict[str, object]:
        reason = normalize_text(params.get("reason"))
        grant_root = normalize_text(params.get("grantRoot"))
        detail_lines = ["Codex wants permission to apply file changes."]
        if grant_root:
            detail_lines.append(f"Grant root: `{grant_root}`")
        if reason:
            detail_lines.append(f"Reason: {reason}")
        pending = PendingInteraction(
            interaction_id=uuid.uuid4().hex[:12],
            kind="file_change_approval",
            title="File Change Approval Required",
            detail="\n".join(detail_lines),
            prompt_text="Choose one of the approval buttons, or reply with: accept / session / decline / cancel.",
            future=asyncio.get_running_loop().create_future(),
            abort_resolution=InteractionResolution({"decision": "cancel"}, "Cancelled", state="cancelled"),
            text_handler=self._decision_text_handler(
                {
                    "accept": InteractionResolution({"decision": "accept"}, "Accept once"),
                    "acceptForSession": InteractionResolution({"decision": "acceptForSession"}, "Accept for session"),
                    "decline": InteractionResolution({"decision": "decline"}, "Decline", state="cancelled"),
                    "cancel": InteractionResolution({"decision": "cancel"}, "Cancel turn", state="cancelled"),
                }
            ),
            command_resolutions={
                "accept": InteractionResolution({"decision": "accept"}, "Allow once"),
                "accept_session": InteractionResolution({"decision": "acceptForSession"}, "Allow for session"),
                "decline": InteractionResolution({"decision": "decline"}, "Decline", state="cancelled"),
                "cancel": InteractionResolution({"decision": "cancel"}, "Cancel turn", state="cancelled"),
            },
        )
        return (await self._await_pending(pending)).response

    async def _request_permissions_approval(self, params: dict[str, object]) -> dict[str, object]:
        permissions = params.get("permissions") if isinstance(params.get("permissions"), dict) else {}
        reason = normalize_text(params.get("reason"))
        detail_lines = format_permissions(permissions)
        if reason:
            detail_lines.append(f"Reason: {reason}")
        if not detail_lines:
            detail_lines.append("No additional permission details were provided.")
        pending = PendingInteraction(
            interaction_id=uuid.uuid4().hex[:12],
            kind="permissions_approval",
            title="Additional Permissions Requested",
            detail="\n".join(detail_lines),
            prompt_text="Choose Accept or Decline, or reply with: accept / decline.",
            future=asyncio.get_running_loop().create_future(),
            abort_resolution=InteractionResolution({"permissions": {}}, "Declined", state="cancelled"),
            text_handler=self._decision_text_handler(
                {
                    "accept": InteractionResolution({"permissions": permissions}, "Accepted requested permissions"),
                    "decline": InteractionResolution({"permissions": {}}, "Declined", state="cancelled"),
                }
            ),
            command_resolutions={
                "accept": InteractionResolution({"permissions": permissions}, "Accept"),
                "decline": InteractionResolution({"permissions": {}}, "Decline", state="cancelled"),
            },
        )
        return (await self._await_pending(pending)).response

    async def _request_tool_user_input(self, params: dict[str, object]) -> dict[str, object]:
        questions = params.get("questions") if isinstance(params.get("questions"), list) else []
        answers: dict[str, dict[str, list[str]]] = {}
        total = len(questions)
        for index, raw_question in enumerate(questions, start=1):
            question = raw_question if isinstance(raw_question, dict) else {}
            resolution = await self._ask_tool_question(question, index=index, total=total)
            if resolution.state in {"cancelled", "canceled"}:
                break
            question_id = str(question.get("id") or f"q_{index}")
            answers[question_id] = {"answers": [str(item) for item in resolution.response.get("answers") or [] if str(item).strip()]}
        return {"answers": answers}

    async def _ask_tool_question(self, question: dict[str, Any], *, index: int, total: int) -> InteractionResolution:
        question_id = str(question.get("id") or f"q_{index}")
        header = shorten(question.get("header") or f"Question {index}", 80)
        prompt = str(question.get("question") or "").strip() or header
        options = question.get("options") if isinstance(question.get("options"), list) else []
        allows_other = bool(question.get("isOther"))
        is_secret = bool(question.get("isSecret"))
        detail_lines = [prompt, f"Question {index}/{total}", f"ID: `{question_id}`"]
        if is_secret:
            detail_lines.append("Warning: Feishu replies are visible in the thread. Do not paste secrets unless you accept that tradeoff.")
        command_resolutions: dict[str, InteractionResolution] = {}
        for option_index, raw_option in enumerate(options):
            option = raw_option if isinstance(raw_option, dict) else {}
            label = str(option.get("label") or "").strip()
            description = str(option.get("description") or "").strip()
            if label:
                detail_lines.append(f"- {label}: {description}" if description else f"- {label}")
                command_resolutions[f"choice_{option_index}"] = InteractionResolution({"answers": [label]}, label)

        def text_handler(text: str) -> InteractionResolution | None:
            normalized = text.strip()
            if not normalized:
                return None
            for option in options:
                if not isinstance(option, dict):
                    continue
                label = str(option.get("label") or "").strip()
                if label and normalized.casefold() == label.casefold():
                    return InteractionResolution({"answers": [label]}, label)
            return InteractionResolution({"answers": [normalized]}, normalized)

        pending = PendingInteraction(
            interaction_id=uuid.uuid4().hex[:12],
            kind="tool_user_input",
            title=f"User Input Requested · {header}",
            detail="\n".join(detail_lines),
            prompt_text=(
                "Choose one of the option buttons, or reply with a free-form answer in the thread."
                if command_resolutions
                else "Reply with your answer in the thread."
            ),
            future=asyncio.get_running_loop().create_future(),
            abort_resolution=InteractionResolution({"answers": []}, "Skipped", state="cancelled"),
            text_handler=text_handler,
            command_resolutions=command_resolutions or None,
        )
        return await self._await_pending(pending)

    async def _request_mcp_elicitation(self, params: dict[str, object]) -> dict[str, object]:
        mode = normalize_text(params.get("mode")).lower()
        if mode == "url":
            return await self._request_mcp_url_elicitation(params)
        if mode == "form":
            return await self._request_mcp_form_elicitation(params)
        return {"action": "decline"}

    async def _request_mcp_url_elicitation(self, params: dict[str, object]) -> dict[str, object]:
        message = normalize_text(params.get("message"))
        url = normalize_text(params.get("url"))
        detail_lines = [message or "External action required."]
        if url:
            detail_lines.append(f"URL: {url}")
        pending = PendingInteraction(
            interaction_id=uuid.uuid4().hex[:12],
            kind="mcp_url_elicitation",
            title="External Authorization Required",
            detail="\n".join(detail_lines),
            prompt_text="Open the URL if needed, then choose Accept, Decline, or Cancel.",
            future=asyncio.get_running_loop().create_future(),
            abort_resolution=InteractionResolution({"action": "cancel"}, "Cancelled", state="cancelled"),
            text_handler=self._decision_text_handler(
                {
                    "accept": InteractionResolution({"action": "accept"}, "Accepted"),
                    "decline": InteractionResolution({"action": "decline"}, "Declined", state="cancelled"),
                    "cancel": InteractionResolution({"action": "cancel"}, "Cancelled", state="cancelled"),
                }
            ),
            command_resolutions={
                "accept": InteractionResolution({"action": "accept"}, "Accept"),
                "decline": InteractionResolution({"action": "decline"}, "Decline", state="cancelled"),
                "cancel": InteractionResolution({"action": "cancel"}, "Cancel", state="cancelled"),
            },
        )
        return (await self._await_pending(pending)).response

    async def _request_mcp_form_elicitation(self, params: dict[str, object]) -> dict[str, object]:
        message = normalize_text(params.get("message"))
        requested_schema = params.get("requestedSchema")
        schema_preview = json.dumps(requested_schema, ensure_ascii=False, indent=2) if requested_schema is not None else "{}"

        def text_handler(text: str) -> InteractionResolution | None:
            raw = strip_code_fences(text)
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return None
            return InteractionResolution({"action": "accept", "content": parsed}, "Submitted form payload", detail=shorten(raw, 240))

        pending = PendingInteraction(
            interaction_id=uuid.uuid4().hex[:12],
            kind="mcp_form_elicitation",
            title="Structured User Input Required",
            detail="\n".join(
                [
                    message or "Provide JSON that matches the requested schema.",
                    "Reply with raw JSON in the thread.",
                    f"Schema:\n```json\n{schema_preview}\n```",
                ]
            ),
            prompt_text="Reply with valid JSON for the requested schema, or choose Decline / Cancel.",
            future=asyncio.get_running_loop().create_future(),
            abort_resolution=InteractionResolution({"action": "cancel"}, "Cancelled", state="cancelled"),
            text_handler=text_handler,
            command_resolutions={
                "decline": InteractionResolution({"action": "decline"}, "Decline", state="cancelled"),
                "cancel": InteractionResolution({"action": "cancel"}, "Cancel", state="cancelled"),
            },
        )
        return (await self._await_pending(pending)).response

    def _decision_text_handler(self, mapping: dict[str, InteractionResolution]) -> Callable[[str], InteractionResolution | None]:
        aliases = {
            "accept": {"accept", "approved", "approve", "allow", "yes", "y", "ok", "允许", "同意"},
            "acceptForSession": {"session", "acceptforsession", "allow-session", "这次会话都允许"},
            "decline": {"decline", "deny", "denied", "reject", "no", "n", "拒绝", "不同意"},
            "cancel": {"cancel", "abort", "stop", "取消"},
        }

        def handler(text: str) -> InteractionResolution | None:
            normalized = normalize_decision_text(text)
            for key, resolution in mapping.items():
                if normalized in {alias.casefold() for alias in aliases.get(key, set())}:
                    return resolution
            return None

        return handler
