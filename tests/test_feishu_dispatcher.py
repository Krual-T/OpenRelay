import asyncio
from pathlib import Path

from openrelay.config import AppConfig, BackendConfig, FeishuConfig
from openrelay.feishu import FeishuEventDispatcher



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
