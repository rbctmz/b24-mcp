from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .bitrix_client import BitrixClient
from .mcp.routes import OAUTH_DISCOVERY_PAYLOAD, router as mcp_router
from .mcp.resources import ResourceRegistry
from .mcp.tools import ToolRegistry
from .settings import AppSettings


def create_app() -> FastAPI:
    settings = AppSettings()
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
        allow_origins=["*"],  # В продакшене укажите конкретные домены
        allow_credentials=True,
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
