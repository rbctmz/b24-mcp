from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class BitrixSettings(BaseSettings):
    """Application configuration sourced from environment variables or .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="BITRIX_", extra="ignore")

    base_url: HttpUrl = Field(..., description="Base REST endpoint, e.g. https://example.bitrix24.ru/rest")
    token: str = Field(..., description="Webhook or OAuth token to authorize REST calls")
    timeout_seconds: float = Field(10.0, ge=1.0, description="HTTP client timeout (seconds)")
    verify_ssl: bool = Field(True, description="Whether to verify SSL certificates")
    retries: int = Field(3, ge=0, le=10, description="Number of retry attempts for transient errors")
    instance_name: Optional[str] = Field(
        None, description="Optional logical name of the Bitrix24 instance for logging/metadata"
    )


class ServerSettings(BaseSettings):
    """FastAPI server configuration."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SERVER_", extra="ignore")

    host: str = Field("0.0.0.0", description="Host interface for uvicorn")
    port: int = Field(8000, ge=1, le=65535, description="Port exposed by the API server")
    log_level: Literal["critical", "error", "warning", "info", "debug", "trace"] = Field(
        "info", description="Logging level for the ASGI server"
    )
    timezone: str = Field(
        "UTC",
        description="IANA timezone used to format date ranges and hints in structured responses",
    )


def _default_bitrix_settings() -> BitrixSettings:
    return BitrixSettings.model_validate({})


def _default_server_settings() -> ServerSettings:
    return ServerSettings.model_validate({})


class AppSettings(BaseModel):
    """Aggregate configuration for the MCP server."""

    bitrix: BitrixSettings = Field(default_factory=_default_bitrix_settings)
    server: ServerSettings = Field(default_factory=_default_server_settings)
