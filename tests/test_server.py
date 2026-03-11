from pathlib import Path

from openrelay.config import AppConfig, BackendConfig, FeishuConfig
from openrelay.server import create_app, resolve_bind_host


def make_config(connection_mode: str) -> AppConfig:
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
            connection_mode=connection_mode,
            bot_open_id="ou_bot",
        ),
        backend=BackendConfig(codex_sessions_dir=base / "native"),
    )


def route_paths(app) -> set[str]:
    return {route.path for route in app.router.routes}


def test_websocket_mode_binds_to_loopback_and_disables_webhook_route() -> None:
    config = make_config("websocket")
    app = create_app(config)

    assert resolve_bind_host(config) == "127.0.0.1"
    assert "/health" in route_paths(app)
    assert config.webhook_path not in route_paths(app)


def test_webhook_mode_binds_to_all_interfaces_and_registers_webhook_route() -> None:
    config = make_config("webhook")
    app = create_app(config)

    assert resolve_bind_host(config) == "0.0.0.0"
    assert "/health" in route_paths(app)
    assert config.webhook_path in route_paths(app)
