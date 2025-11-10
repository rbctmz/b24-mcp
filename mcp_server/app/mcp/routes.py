from __future__ import annotations

from typing import Any, Dict, Optional
import asyncio
import json
from starlette.responses import StreamingResponse, JSONResponse

from fastapi import APIRouter, Body, Depends, Request, Response, WebSocket, WebSocketDisconnect

from ..dependencies import get_resource_registry, get_tool_registry
from ..mcp.resources import ResourceRegistry
from ..mcp.tools import ToolRegistry
from .schemas import MCPIndexResponse, ResourceQueryRequest, ResourceQueryResponse, ToolCallRequest, ToolCallResponse

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])

_HEALTH_PAYLOAD: Dict[str, str] = {"status": "ok", "message": "MCP endpoint is alive"}
OAUTH_DISCOVERY_PAYLOAD: Dict[str, str] = {
    "status": "ok",
    "message": "OAuth discovery metadata is not configured for this MCP server.",
}


@router.get("/index", response_model=MCPIndexResponse)
async def mcp_index(
    resource_registry: ResourceRegistry = Depends(get_resource_registry),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
) -> MCPIndexResponse:
    return MCPIndexResponse(resources=resource_registry.descriptors(), tools=tool_registry.descriptors())


def _handshake_payload(
    request: Request | WebSocket,
    resource_registry: ResourceRegistry,
    tool_registry: ToolRegistry,
) -> Dict[str, Any]:
    resource_descriptors = resource_registry.descriptors()
    tool_descriptors = tool_registry.descriptors()

    response: Dict[str, Any] = {
        "serverInfo": {
            "name": request.app.title or "Bitrix24 MCP Server",
            "version": request.app.version or "0.1.0",
        },
        "protocolVersion": {
            "major": 1,
            "minor": 0,
        },
        "capabilities": {
            "resources": {
                "list": {},
                "query": {},
            },
            "tools": {
                "list": {},
                "call": {},
            },
        },
        "instructions": request.app.description or "Access Bitrix24 CRM data via MCP resources and tools.",
        "resources": [descriptor.model_dump() for descriptor in resource_descriptors],
        "tools": [descriptor.model_dump() for descriptor in tool_descriptors],
    }

    return response


# Simple in-process SSE broadcaster for connected clients. Each client gets
# an asyncio.Queue where server code can place JSON-serializable payloads
# which will be sent as SSE `data:` events. This is intentionally lightweight
# and suitable for local/dev usage; for production multi-instance setups use
# Redis/other pubsub to fan-out events across processes.
SSE_CLIENTS: set[asyncio.Queue] = set()


async def _broadcast_sse(payload: Dict[str, Any]) -> None:
    if not SSE_CLIENTS:
        return
    for q in list(SSE_CLIENTS):
        try:
            # Use put_nowait so a slow client won't block the broadcaster.
            q.put_nowait(payload)
        except asyncio.QueueFull:
            # Drop message for full queues; client is likely slow.
            continue


@router.get("")
async def mcp_healthcheck(request: Request) -> Response:
    accept_header = request.headers.get("accept", "")
    if "text/event-stream" in accept_header.lower():
        return await mcp_sse(request)
    return JSONResponse(_HEALTH_PAYLOAD)


@router.options("")
async def mcp_options(request: Request) -> Response:
    origin = request.headers.get("origin", "*")
    allow_headers = request.headers.get("access-control-request-headers", "*")

    return Response(
        content=None,
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": allow_headers,
            "Access-Control-Max-Age": "600",
        },
    )


@router.post("")
async def mcp_handshake(
    request: Request,
    resource_registry: ResourceRegistry = Depends(get_resource_registry),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
) -> Any:
    """Handle MCP JSON-RPC 2.0 requests including initialize."""
    
    # Попытка прочитать тело запроса разными способами
    try:
        body = await request.json()
        logger.info(f"MCP request: {body}")
    except Exception:
        # Если не удалось распарсить как JSON, пытаемся прочитать как строку
        try:
            body_bytes = await request.body()
            if not body_bytes:
                logger.warning("Empty request body")
                return {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": "Parse error: empty request body"
                    }
                }
            import json
            body = json.loads(body_bytes.decode('utf-8'))
            logger.info(f"MCP request (parsed from bytes): {body}")
        except Exception as e:
            logger.error(f"Failed to parse request body: {e}")
            return {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": f"Parse error: {str(e)}"
                }
            }
    
    # Если это JSON-RPC 2.0 запрос
    if body and isinstance(body, dict) and "jsonrpc" in body:
        request_id = body.get("id")
        method = body.get("method", "")
        params = body.get("params", {})
        
        logger.info(f"Processing JSON-RPC method: {method}, id: {request_id}")
        
        # Уведомления (notifications) не требуют ответа
        if request_id is None:
            if method == "initialized":
                logger.info("Received initialized notification")
                return Response(status_code=204)  # No Content для notifications
            else:
                logger.warning(f"Unknown notification method: {method}")
                return Response(status_code=204)
        
        # Обработка метода initialize
        if method == "initialize":
            logger.info("Processing initialize request")
            result = _handshake_payload(request, resource_registry, tool_registry)
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }
            logger.info(f"Initialize response: {response}")
            # Broadcast initialize result to any SSE-connected clients as well
            try:
                asyncio.create_task(_broadcast_sse({"type": "initialize", "id": request_id, "result": result}))
            except Exception:
                logger.exception("Failed to broadcast initialize to SSE clients")
            return response
        # Обработка других методов (tools/call, resources/query и т.д.)
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_params = params.get("arguments", {})
            if not tool_name:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": "Invalid params: tool name required"
                    }
                }
            tool_request = ToolCallRequest(tool=tool_name, params=tool_params)
            response = await tool_registry.call(tool_request)
            # Broadcast tool call result to SSE clients
            try:
                asyncio.create_task(_broadcast_sse({"type": "tools/call", "id": request_id, "result": response.model_dump()}))
            except Exception:
                logger.exception("Failed to broadcast tools/call to SSE clients")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": response.model_dump()
            }
        elif method == "resources/query":
            resource_name = params.get("uri")
            resource_params = params.get("arguments", {})
            cursor = params.get("cursor")
            if not resource_name:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": "Invalid params: resource uri required"
                    }
                }
            resource_request = ResourceQueryRequest(
                resource=resource_name,
                params=resource_params,
                cursor=cursor
            )
            response = await resource_registry.query(resource_request)
            # Broadcast resource query result to SSE clients
            try:
                asyncio.create_task(_broadcast_sse({"type": "resources/query", "id": request_id, "result": response.model_dump()}))
            except Exception:
                logger.exception("Failed to broadcast resources/query to SSE clients")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": response.model_dump()
            }
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [tool.model_dump() for tool in tool_registry.descriptors()]
                }
            }
        elif method == "resources/list":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "resources": [res.model_dump() for res in resource_registry.descriptors()]
                }
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }
    else:
        # Обратная совместимость: при получении простого JSON возвращаем payload handshake
        return _handshake_payload(request, resource_registry, tool_registry)


@router.post("/initialize")
async def mcp_initialize(
    request: Request,
    rpc_request: Optional[Dict[str, Any]] = Body(default=None),
    resource_registry: ResourceRegistry = Depends(get_resource_registry),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
) -> Dict[str, Any]:
    """Endpoint compatible with MCP JSON-RPC 2.0 protocol."""
    
    # Поддержка JSON-RPC 2.0 формата
    if rpc_request and "jsonrpc" in rpc_request:
        # Это JSON-RPC запрос
        request_id = rpc_request.get("id")
        result = _handshake_payload(request, resource_registry, tool_registry)
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result
        }
    else:
        # Обратная совместимость со старым форматом
        payload = _handshake_payload(request, resource_registry, tool_registry)
        try:
            asyncio.create_task(_broadcast_sse({"type": "initialize", "id": None, "result": payload}))
        except Exception:
            logger.exception("Failed to broadcast initialize to SSE clients (initialize endpoint)")
        return payload


@router.get("/.well-known/oauth-authorization-server")
async def mcp_oauth_discovery_root() -> Dict[str, str]:
    return dict(OAUTH_DISCOVERY_PAYLOAD)


@router.get("/.well-known/oauth-authorization-server/{_suffix:path}")
async def mcp_oauth_discovery_suffix(_suffix: str) -> Dict[str, str]:
    return dict(OAUTH_DISCOVERY_PAYLOAD)


@router.post("/resource/query", response_model=ResourceQueryResponse)
async def resource_query(
    request: ResourceQueryRequest,
    resource_registry: ResourceRegistry = Depends(get_resource_registry),
) -> ResourceQueryResponse:
    resp = await resource_registry.query(request)
    # Broadcast results to SSE clients
    try:
        asyncio.create_task(_broadcast_sse({"type": "resources/query", "id": None, "result": resp.model_dump()}))
    except Exception:
        logger.exception("Failed to broadcast resources/query from /resource/query endpoint")
    return resp


@router.post("/tool/call", response_model=ToolCallResponse)
async def tool_call(
    rpc_request: Dict[str, Any] = Body(...),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
) -> Dict[str, Any]:
    """Execute a tool via MCP JSON-RPC 2.0 protocol."""
    
    # Поддержка JSON-RPC 2.0 формата
    if "jsonrpc" in rpc_request:
        request_id = rpc_request.get("id")
        method = rpc_request.get("method", "")
        params = rpc_request.get("params", {})
        
        # Извлечь tool и params из метода или params
        if method == "tools/call":
            tool_name = params.get("name")
            tool_params = params.get("arguments", {})
        else:
            # Старый формат для обратной совместимости
            tool_name = rpc_request.get("tool")
            tool_params = rpc_request.get("params", {})
        
        if not tool_name:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32602,
                    "message": "Invalid params: tool name required"
                }
            }
        
        tool_request = ToolCallRequest(tool=tool_name, params=tool_params)
        response = await tool_registry.call(tool_request)

        # Also broadcast tool result to SSE clients
        try:
            asyncio.create_task(_broadcast_sse({"type": "tools/call", "id": request_id, "result": response.model_dump()}))
        except Exception:
            logger.exception("Failed to broadcast tools/call from /tool/call endpoint")

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": response.model_dump()
        }
    else:
        # Старый формат для обратной совместимости
        tool_request = ToolCallRequest(**rpc_request)
        response = await tool_registry.call(tool_request)
        return response.model_dump()


@router.websocket("")
async def mcp_websocket(websocket: WebSocket) -> None:
    """WebSocket transport for MCP JSON-RPC messages at path `/mcp`.

    This mirrors the HTTP JSON-RPC handlers and allows agents that expect
    a WebSocket transport (e.g. `ws://127.0.0.1:8000/mcp`) to connect.
    """
    await websocket.accept()
    # FastAPI dependency injection for WebSocket endpoints may not resolve
    # the same Request-based dependencies. Read registries directly from
    # application state to avoid dependency resolution errors during the
    # WebSocket handshake.
    resource_registry = getattr(websocket.app.state, "resource_registry", None)
    tool_registry = getattr(websocket.app.state, "tool_registry", None)

    if resource_registry is None or tool_registry is None:
        # Server not initialized correctly; close with server error code
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
        return

    try:
        while True:
            data = await websocket.receive_text()
            import json

            try:
                body = json.loads(data)
            except Exception:
                # Send a JSON-RPC parse error for malformed JSON
                await websocket.send_text(
                    json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
                )
                continue

            # If this looks like JSON-RPC 2.0
            if body and isinstance(body, dict) and "jsonrpc" in body:
                request_id = body.get("id")
                method = body.get("method", "")
                params = body.get("params", {})

                # Notifications (no response required)
                if request_id is None:
                    continue

                if method == "initialize":
                    result = _handshake_payload(websocket, resource_registry, tool_registry)
                    response = {"jsonrpc": "2.0", "id": request_id, "result": result}
                    await websocket.send_text(json.dumps(response))

                elif method == "tools/list":
                    await websocket.send_text(
                        json.dumps({"jsonrpc": "2.0", "id": request_id, "result": {"tools": [t.model_dump() for t in tool_registry.descriptors()]}})
                    )

                elif method == "resources/list":
                    await websocket.send_text(
                        json.dumps({"jsonrpc": "2.0", "id": request_id, "result": {"resources": [r.model_dump() for r in resource_registry.descriptors()]}})
                    )

                elif method == "tools/call":
                    tool_name = params.get("name")
                    tool_params = params.get("arguments", {})
                    if not tool_name:
                        await websocket.send_text(json.dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Invalid params: tool name required"}}))
                        continue
                    tool_request = ToolCallRequest(tool=tool_name, params=tool_params)
                    resp = await tool_registry.call(tool_request)
                    await websocket.send_text(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": resp.model_dump()}))

                elif method == "resources/query":
                    resource_name = params.get("uri")
                    resource_params = params.get("arguments", {})
                    cursor = params.get("cursor")
                    if not resource_name:
                        await websocket.send_text(json.dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Invalid params: resource uri required"}}))
                        continue
                    resource_request = ResourceQueryRequest(resource=resource_name, params=resource_params, cursor=cursor)
                    resp = await resource_registry.query(resource_request)
                    await websocket.send_text(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": resp.model_dump()}))

                else:
                    await websocket.send_text(json.dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}))

            else:
                # Back-compat: send handshake payload if not a JSON-RPC body
                payload = _handshake_payload(websocket, resource_registry, tool_registry)
                await websocket.send_text(json.dumps(payload))

    except WebSocketDisconnect:
        logger.info("MCP websocket client disconnected")
    except Exception:
        logger.exception("Unhandled error in MCP websocket handler")
        try:
            await websocket.close()
        except Exception:
            pass


@router.get("/sse")
async def mcp_sse(request: Request) -> StreamingResponse:
    """Server-Sent Events endpoint at `/mcp/sse`.

    Clients connect via GET and will receive JSON `data:` events. The
    server broadcasts initialize/tool/resource results to connected clients.
    """
    # Obtain registries for initial handshake
    resource_registry = getattr(request.app.state, "resource_registry", None)
    tool_registry = getattr(request.app.state, "tool_registry", None)

    if resource_registry is None or tool_registry is None:
        return StreamingResponse(iter([""],), media_type="text/event-stream", status_code=500)

    async def event_generator(q: asyncio.Queue):
        # Send initial handshake as first event
        try:
            payload = _handshake_payload(request, resource_registry, tool_registry)
            init_event = json.dumps({"type": "initialize", "result": payload})
            yield "data: " + init_event + "\n\n"
        except Exception:
            logger.exception("Failed to send initial handshake over SSE")

        try:
            while True:
                try:
                    item = await q.get()
                except asyncio.CancelledError:
                    break
                try:
                    yield f"data: {json.dumps(item)}\n\n"
                except Exception:
                    logger.exception("Failed to serialize SSE payload")
                    continue
        finally:
            # Generator finished or client disconnected
            return

    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    SSE_CLIENTS.add(q)

    # Build async iterator from event_generator
    async def asgi_iter():
        try:
            async for s in event_generator(q):
                yield s.encode("utf-8")
        finally:
            # Clean up client queue on disconnect
            try:
                SSE_CLIENTS.discard(q)
            except Exception:
                pass

    return StreamingResponse(asgi_iter(), media_type="text/event-stream")
