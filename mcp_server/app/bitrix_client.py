from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

import httpx
from httpx import Response
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from .settings import BitrixSettings

logger = logging.getLogger(__name__)


class BitrixAPIError(RuntimeError):
    """Raised when Bitrix24 returns an error response or unexpected payload."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, payload: Any | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class BitrixClient:
    """Thin async wrapper around Bitrix24 REST API."""

    def __init__(self, settings: BitrixSettings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=str(settings.base_url).rstrip("/"),
            headers={"Content-Type": "application/json"},
            timeout=settings.timeout_seconds,
            verify=settings.verify_ssl,
        )
        self._retry = AsyncRetrying(
            stop=stop_after_attempt(settings.retries + 1),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception_type((httpx.TransportError, BitrixAPIError)),
            reraise=True,
        )
        self._token = settings.token

    @property
    def settings(self) -> BitrixSettings:  # pragma: no cover - trivial accessor
        return self._settings

    async def close(self) -> None:
        await self._client.aclose()

    async def call_method(self, method: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Call Bitrix REST method with retry support."""

        payload = payload or {}
        url = f"/{method}"

        async for attempt in self._retry:
            with attempt:
                response = await self._client.post(
                    url,
                    json=payload_with_auth(payload, self._token),
                )
                data = await self._parse_response(response)
                return data

        raise BitrixAPIError(f"Failed to call {method}")  # pragma: no cover - defensive

    async def _parse_response(self, response: Response) -> Dict[str, Any]:
        """Validate Bitrix REST response structure."""

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise BitrixAPIError("Bitrix returned non-JSON response", status_code=response.status_code) from exc

        if response.status_code >= 400:
            raise BitrixAPIError(
                f"Bitrix returned HTTP {response.status_code}",
                status_code=response.status_code,
                payload=data,
            )

        if "error" in data:
            raise BitrixAPIError(
                f"Bitrix error: {data.get('error_description') or data['error']}",
                status_code=response.status_code,
                payload=data,
            )

        if "result" not in data:
            raise BitrixAPIError(
                "Bitrix response missing 'result' field",
                status_code=response.status_code,
                payload=data,
            )

        return data


def payload_with_auth(payload: Dict[str, Any], token: str) -> Dict[str, Any]:
    """Attach authorization token if it is not already present."""

    if "auth" in payload:
        return payload
    merged = dict(payload)
    merged["auth"] = token
    return merged
