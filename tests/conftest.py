from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_server.app import create_app  # noqa: E402
import mcp_server.app.main as main_module  # noqa: E402


class StubBitrixClient:
    """In-memory Bitrix client used for isolating tests from HTTP layer."""

    def __init__(self, settings) -> None:
        self.settings = settings
        self.responses: Dict[str, Any] = {}
        self.calls: List[Tuple[str, Dict[str, Any]]] = []
        self._default_responses = {
            "crm.status.list": lambda payload: {"result": []},
            "crm.lead.list": lambda payload: {"result": []},
            "crm.currency.list": lambda payload: {"result": []},
            "user.get": lambda payload: {
                "result": {
                    "ID": payload.get("ID"),
                    "NAME": "User",
                    "LAST_NAME": "Potato",
                }
            },
        }

    async def call_method(self, method: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        self.calls.append((method, payload or {}))
        if method not in self.responses:
            default = self._default_responses.get(method)
            if callable(default):
                return default(payload or {})
            raise AssertionError(f"Unexpected Bitrix method '{method}' invoked without stub")
        response = self.responses[method]
        if callable(response):
            result = response(payload or {})
        else:
            result = response
        if isinstance(result, Exception):
            raise result
        return result

    async def close(self) -> None:
        return None


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("BITRIX_BASE_URL", "https://bitrix.test/rest")
    monkeypatch.setenv("BITRIX_TOKEN", "test-token")
    monkeypatch.setenv("SERVER_HOST", "127.0.0.1")
    monkeypatch.setenv("SERVER_PORT", "9000")
    monkeypatch.setattr(main_module, "BitrixClient", StubBitrixClient)
    application = create_app()
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
