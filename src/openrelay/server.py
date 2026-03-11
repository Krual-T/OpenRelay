from __future__ import annotations

import asyncio
import json
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
import uvicorn

from openrelay.config import AppConfig, ConfigError, load_config
from openrelay.feishu import FeishuEventDispatcher, FeishuMessenger, build_raw_request
from openrelay.feishu_ws import FeishuWebSocketClient
from openrelay.runtime import AgentRuntime
from openrelay.state import StateStore


LOGGER = logging.getLogger("openrelay")



def _should_use_validated_handler(config: AppConfig) -> bool:
    return bool(config.feishu.verify_token)


def _should_register_webhook_route(config: AppConfig) -> bool:
    return config.feishu.connection_mode == "webhook"


def resolve_bind_host(config: AppConfig) -> str:
    if config.feishu.connection_mode == "websocket":
        return "127.0.0.1"
    return "0.0.0.0"



def create_app(config: AppConfig | None = None) -> FastAPI:
    app_config = config or load_config()
    app = FastAPI(title="openrelay", version="0.1.0")

    @app.on_event("startup")
    async def on_startup() -> None:
        logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
        store = StateStore(app_config)
        messenger = FeishuMessenger(app_config)
        runtime = AgentRuntime(app_config, store, messenger)
        event_dispatcher = FeishuEventDispatcher(app_config, asyncio.get_running_loop(), runtime.dispatch_message, messenger=messenger)
        app.state.config = app_config
        app.state.store = store
        app.state.messenger = messenger
        app.state.runtime = runtime
        app.state.event_handler = event_dispatcher.build()
        app.state.ws_client = None
        try:
            await messenger.resolve_bot_open_id()
        except Exception as exc:
            LOGGER.warning("failed to resolve Feishu bot open id: %s", exc)
        if app_config.feishu.connection_mode == "websocket":
            ws_client = FeishuWebSocketClient(app_config, app.state.event_handler)
            await ws_client.start()
            app.state.ws_client = ws_client
        bind_host = resolve_bind_host(app_config)
        if _should_register_webhook_route(app_config):
            LOGGER.info("openrelay listening on http://%s:%s%s", bind_host, app_config.port, app_config.webhook_path)
        else:
            LOGGER.info("openrelay listening on http://%s:%s (websocket mode; webhook disabled)", bind_host, app_config.port)

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        ws_client = getattr(app.state, "ws_client", None)
        if ws_client is not None:
            await ws_client.close()
        runtime: AgentRuntime = app.state.runtime
        await runtime.shutdown()

    @app.get("/health")
    async def health() -> dict[str, object]:
        runtime: AgentRuntime = app.state.runtime
        return {
            "ok": True,
            "default_backend": app_config.backend.default_backend,
            "available_backends": runtime.available_backend_names(),
            "workspace_root": str(app_config.workspace_root),
            "active_runs": len(runtime.active_runs),
            "feishu_connection_mode": app_config.feishu.connection_mode,
            "feishu_ws_connected": bool(getattr(app.state, "ws_client", None) is not None and getattr(app.state.ws_client, "connected", False)),
        }

    if _should_register_webhook_route(app_config):
        @app.post(app_config.webhook_path)
        async def feishu_webhook(request: Request) -> Response:
            content_length = request.headers.get("content-length", "")
            if content_length:
                try:
                    if int(content_length) > app_config.max_request_bytes:
                        raise HTTPException(status_code=413, detail="request body too large")
                except ValueError:
                    pass
            body_bytes = await request.body()
            if len(body_bytes) > app_config.max_request_bytes:
                raise HTTPException(status_code=413, detail="request body too large")
            try:
                body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc

            event_handler = app.state.event_handler
            if _should_use_validated_handler(app_config):
                raw_request = build_raw_request(request.url.path, dict(request.headers.items()), body_bytes)
                raw_response = event_handler.do(raw_request)
                return Response(content=raw_response.content or b"", status_code=raw_response.status_code, headers=raw_response.headers)

            webhook_type = body.get("type") if isinstance(body, dict) else ""
            if webhook_type == "url_verification":
                return JSONResponse({"challenge": body.get("challenge", "")})

            try:
                result = event_handler.do_without_validation(body_bytes)
            except Exception as exc:
                LOGGER.exception("failed handling Feishu webhook without validation")
                return JSONResponse({"msg": str(exc)}, status_code=500)
            if result is None:
                return JSONResponse({"msg": "success"})
            return JSONResponse(result)

    return app



def main() -> None:
    try:
        config = load_config()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc
    uvicorn.run(create_app(config), host=resolve_bind_host(config), port=config.port)
