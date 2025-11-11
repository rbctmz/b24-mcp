#!/usr/bin/env python3
"""Claude Desktop stdio ↔ Bitrix24 MCP HTTP proxy."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Awaitable, Callable, Dict, Optional

import httpx


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = 30.0


class ProxyConfig:
    """Runtime configuration resolved from environment."""

    def __init__(self) -> None:
        self.base_url = os.environ.get("MCP_PROXY_BASE_URL", DEFAULT_BASE_URL)
        timeout_raw = os.environ.get("MCP_PROXY_TIMEOUT", str(DEFAULT_TIMEOUT))
        try:
            self.timeout = float(timeout_raw)
        except ValueError:
            self.timeout = DEFAULT_TIMEOUT


CONFIG = ProxyConfig()


async def _get_index(client: httpx.AsyncClient) -> Dict[str, Any]:
    response = await client.get("/mcp/index")
    response.raise_for_status()
    return response.json()


async def _handle_initialize(
    client: httpx.AsyncClient, req_id: Any, params: Dict[str, Any]
) -> Dict[str, Any]:
    data = await _get_index(client)
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "protocolVersion": data.get("protocolVersion", "2025-06-18"),
            "capabilities": data.get("capabilities", {}),
            "serverInfo": data.get(
                "serverInfo",
                {"name": "bitrix24-mcp", "version": "1.0.0"},
            ),
        },
    }


async def _handle_resources_list(
    client: httpx.AsyncClient, req_id: Any, params: Dict[str, Any]
) -> Dict[str, Any]:
    data = await _get_index(client)
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {"resources": data.get("resources", [])},
    }


async def _handle_resources_read(
    client: httpx.AsyncClient, req_id: Any, params: Dict[str, Any]
) -> Dict[str, Any]:
    uri = params.get("uri", "")
    response = await client.post(
        "/mcp/resource/query",
        json={"resource": uri, "params": params},
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(payload),
                }
            ]
        },
    }


async def _handle_tools_list(
    client: httpx.AsyncClient, req_id: Any, params: Dict[str, Any]
) -> Dict[str, Any]:
    data = await _get_index(client)
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {"tools": data.get("tools", [])},
    }


async def _handle_tools_call(
    client: httpx.AsyncClient, req_id: Any, params: Dict[str, Any]
) -> Dict[str, Any]:
    tool_name = params.get("name")
    tool_params = params.get("arguments", {})
    response = await client.post(
        "/mcp/tool/call",
        json={"tool": tool_name, "params": tool_params},
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(payload),
                }
            ]
        },
    }


Handler = Callable[[httpx.AsyncClient, Any, Dict[str, Any]], Awaitable[Dict[str, Any]]]


async def handle_request(request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Forward JSON-RPC request to HTTP MCP server."""

    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")
    is_notification = req_id is None

    if not isinstance(method, str):
        if is_notification:
            return None
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32600, "message": "Invalid method name"},
        }

    if not isinstance(params, dict):
        if is_notification:
            return None
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32602, "message": "Invalid params"},
        }

    handlers: Dict[str, Handler] = {
        "initialize": _handle_initialize,
        "resources/list": _handle_resources_list,
        "resources/read": _handle_resources_read,
        "tools/list": _handle_tools_list,
        "tools/call": _handle_tools_call,
    }

    handler = handlers.get(method)
    if handler is None:
        if is_notification:
            return None
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    async with httpx.AsyncClient(base_url=CONFIG.base_url, timeout=CONFIG.timeout) as client:
        try:
            result = await handler(client, req_id, params)
            if is_notification:
                return None
            return result
        except httpx.HTTPStatusError as exc:
            if is_notification:
                return None
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": exc.response.status_code,
                    "message": exc.response.text,
                },
            }
        except Exception as exc:  # noqa: BLE001 - bubble up details for debugging
            if is_notification:
                return None
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(exc)},
            }


async def main() -> None:
    """Read JSON-RPC from stdin, forward to HTTP server, write to stdout."""

    try:
        for line in sys.stdin:
            try:
                request = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            response = await handle_request(request)
            if response is None:
                continue

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    except BrokenPipeError:
        # Client closed connection, exit gracefully.
        pass


if __name__ == "__main__":
    asyncio.run(main())
