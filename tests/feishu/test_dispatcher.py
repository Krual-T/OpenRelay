import asyncio
from pathlib import Path

from openrelay.core import AppConfig, BackendConfig, FeishuConfig
from openrelay.feishu import FeishuEventDispatcher
from openrelay.core import IncomingMessage



def make_config() -> AppConfig:
    base = Path.cwd()
    return AppConfig(
        cwd=base,
        port=3100,
        webhook_path="/feishu/webhook",
        data_dir=base / "data",
        workspace_root=base,
        main_workspace_dir=base,
        develop_workspace_dir=base,
        max_request_bytes=1024,
        max_session_messages=20,
        feishu=FeishuConfig(
            app_id="app",
            app_secret="secret",
            verify_token="verify-token",
            bot_open_id="ou_bot",
        ),
        backend=BackendConfig(codex_sessions_dir=base / "native"),
    )



def test_official_feishu_dispatcher_builds() -> None:
    loop = asyncio.new_event_loop()
    try:
        dispatcher = FeishuEventDispatcher(make_config(), loop, lambda message: asyncio.sleep(0))
        handler = dispatcher.build()
        assert handler is not None
    finally:
        loop.close()


class FakeMessenger:
    async def download_message_resource_to_file(self, message_id: str, file_key: str, *, resource_type: str = "image") -> str:
        assert message_id == "om_image_1"
        assert file_key == "img_v2_123"
        assert resource_type == "image"
        return "/tmp/feishu-image.png"


def test_feishu_dispatcher_resolves_remote_image_keys() -> None:
    dispatched: list[IncomingMessage] = []

    async def dispatch_message(message: IncomingMessage) -> None:
        dispatched.append(message)

    loop = asyncio.new_event_loop()
    try:
        dispatcher = FeishuEventDispatcher(make_config(), loop, dispatch_message, messenger=FakeMessenger())
        loop.run_until_complete(
            dispatcher._dispatch_with_media_resolution(
                IncomingMessage(
                    event_id="evt_image_1",
                    message_id="om_image_1",
                    chat_id="oc_1",
                    chat_type="p2p",
                    sender_open_id="ou_user",
                    text="[图片]",
                    remote_image_keys=("img_v2_123",),
                    actionable=True,
                )
            )
        )
    finally:
        loop.close()

    assert len(dispatched) == 1
    assert dispatched[0].remote_image_keys == ()
    assert dispatched[0].local_image_paths == ("/tmp/feishu-image.png",)
