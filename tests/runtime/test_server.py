from pathlib import Path

from openrelay.server import create_app, resolve_bind_host
from tests.support.app import make_app_config


def make_config(connection_mode: str):
    base = Path.cwd()
    return make_app_config(
        base,
        data_dir=base / "data",
        workspace_root=base,
        main_workspace_dir=base,
        develop_workspace_dir=base,
        codex_sessions_dir=base / "native",
        verify_token=None,
        connection_mode=connection_mode,
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
