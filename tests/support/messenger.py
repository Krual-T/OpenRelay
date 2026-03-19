class RecordingInteractiveMessenger:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls: list[dict[str, object]] = []

    async def send_interactive_card(
        self,
        chat_id: str,
        card: dict[str, object],
        *,
        reply_to_message_id: str = "",
        root_id: str = "",
        force_new_message: bool = False,
        update_message_id: str = "",
    ) -> object:
        self.calls.append(
            {
                "chat_id": chat_id,
                "card": card,
                "reply_to_message_id": reply_to_message_id,
                "root_id": root_id,
                "force_new_message": force_new_message,
                "update_message_id": update_message_id,
            }
        )
        if self.should_fail:
            raise RuntimeError("boom")
        return object()
