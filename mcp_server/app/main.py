from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .bitrix_client import BitrixClient
from .mcp.routes import OAUTH_DISCOVERY_PAYLOAD, router as mcp_router
from .mcp.resources import ResourceRegistry
from .mcp.tools import ToolRegistry
from .settings import AppSettings


LOG_NAMES_TO_SYNC = (
    "",
    "mcp_server",
    "mcp_server.app",
    "mcp_server.app.mcp",
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
)


def _configure_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    # Ensure basicConfig is applied at least once; subsequent calls are harmless
    logging.basicConfig(level=numeric_level)
    for name in LOG_NAMES_TO_SYNC:
        logging.getLogger(name).setLevel(numeric_level)


def create_app() -> FastAPI:
    settings = AppSettings()
    _configure_logging(settings.server.log_level)
    bitrix_client = BitrixClient(settings.bitrix)
    resource_registry = ResourceRegistry(bitrix_client)
    tool_registry = ToolRegistry(bitrix_client)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.bitrix_client = bitrix_client
        app.state.resource_registry = resource_registry
        app.state.tool_registry = tool_registry
        yield
        await bitrix_client.close()

    app = FastAPI(
        title="Bitrix24 MCP Server",
        version="0.1.0",
        description="Model Context Protocol server exposing Bitrix24 data and actions.",
        lifespan=lifespan,
    )

    # Добавляем CORS middleware
    app.add_middleware(
        CORSMiddleware,
        # Для локальной разработки поддерживаем любые порты localhost/127.0.0.1
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz", tags=["health"])
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/.well-known/oauth-authorization-server", tags=["well-known"])
    async def oauth_discovery_root() -> dict[str, str]:
        return dict(OAUTH_DISCOVERY_PAYLOAD)

    @app.get("/.well-known/oauth-authorization-server/{suffix:path}", tags=["well-known"])
    async def oauth_discovery_suffix(suffix: str) -> dict[str, str]:
        _ = suffix
        return dict(OAUTH_DISCOVERY_PAYLOAD)

    app.include_router(mcp_router)
    return app


def main() -> None:  # pragma: no cover
    import uvicorn

    settings = AppSettings()
    uvicorn.run(
        "mcp_server.app.main:create_app",
        host=settings.server.host,
        port=settings.server.port,
        log_level=settings.server.log_level,
        reload=False,
        factory=True,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
