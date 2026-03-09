from __future__ import annotations

import asyncio
import json
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

from openrelay.config import AppConfig, ConfigError, load_config
from openrelay.feishu import FeishuMessenger, parse_webhook_body
from openrelay.feishu_ws import FeishuWebSocketClient
from openrelay.runtime import AgentRuntime
from openrelay.state import StateStore


LOGGER = logging.getLogger("openrelay")



def create_app(config: AppConfig | None = None) -> FastAPI:
    app_config = config or load_config()
    app = FastAPI(title="openrelay", version="0.1.0")

    @app.on_event("startup")
    async def on_startup() -> None:
        logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
        store = StateStore(app_config)
        messenger = FeishuMessenger(app_config)
        runtime = AgentRuntime(app_config, store, messenger)
        app.state.config = app_config
        app.state.store = store
        app.state.messenger = messenger
        app.state.runtime = runtime
        app.state.ws_client = None
        if app_config.feishu.connection_mode == "websocket":
            ws_client = FeishuWebSocketClient(app_config, messenger, runtime.dispatch_message)
            await ws_client.start()
            app.state.ws_client = ws_client
        LOGGER.info("openrelay listening on http://127.0.0.1:%s%s", app_config.port, app_config.webhook_path)

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

    @app.post(app_config.webhook_path)
    async def feishu_webhook(request: Request) -> JSONResponse:
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
        parsed = parse_webhook_body(app_config, body if isinstance(body, dict) else {})
        if parsed.type == "challenge":
            return JSONResponse({"challenge": parsed.challenge})
        if parsed.type == "reject":
            return JSONResponse(parsed.body or {"error": "rejected"}, status_code=parsed.status_code)
        if parsed.type != "message" or parsed.message is None:
            return JSONResponse({"ok": True, "ignored": True})
        runtime: AgentRuntime = app.state.runtime
        asyncio.create_task(runtime.dispatch_message(parsed.message))
        return JSONResponse({"ok": True, "accepted": True})

    return app



def main() -> None:
    try:
        config = load_config()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc
    uvicorn.run(create_app(config), host="0.0.0.0", port=config.port)
