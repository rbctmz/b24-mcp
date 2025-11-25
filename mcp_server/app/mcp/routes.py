from __future__ import annotations

from typing import Any, Dict, Optional
import asyncio
import json
from collections import deque
from starlette.responses import StreamingResponse, JSONResponse

from fastapi import APIRouter, Body, Depends, Request, Response, WebSocket, WebSocketDisconnect

from ..dependencies import get_resource_registry, get_tool_registry
from ..mcp.resources import ResourceRegistry
from ..mcp.tools import ToolRegistry
from .schemas import MCPIndexResponse, ResourceQueryRequest, ResourceQueryResponse, ToolCallRequest
from ..prompt_loader import get_initialize_prompts

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])

_HEALTH_PAYLOAD: Dict[str, str] = {"status": "ok", "message": "MCP endpoint is alive"}
OAUTH_DISCOVERY_PAYLOAD: Dict[str, str] = {
    "status": "ok",
    "message": "OAuth discovery metadata is not configured for this MCP server.",
}


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


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
    initialize_prompts = get_initialize_prompts()
    structured_instructions = initialize_prompts.get("structured", [])
    instruction_notes = initialize_prompts.get("notes", [])
    resource_descriptors = resource_registry.descriptors()
    tool_descriptors = tool_registry.descriptors()

    response: Dict[str, Any] = {
        "serverInfo": {
            "name": request.app.title or "Bitrix24 MCP Server",
            "version": request.app.version or "0.1.0",
        },
        "protocolVersion": "2025-06-18",
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
        "instructions": (
            initialize_prompts.get("summary")
            or request.app.description
            or "Работайте с данными Bitrix24 через ресурсы и инструменты MCP."
        ),
        "resources": [descriptor.model_dump() for descriptor in resource_descriptors],
        "tools": [descriptor.model_dump() for descriptor in tool_descriptors],
    }
    if structured_instructions:
        response["structuredInstructions"] = structured_instructions
    if instruction_notes:
        response["instructionNotes"] = instruction_notes

    return response


# Simple in-process SSE broadcaster for connected clients. Each client gets
# an asyncio.Queue of JSON-RPC messages that will be emitted as SSE `data:`
# events. This is intentionally lightweight and suitable for local/dev usage;
# for production multi-instance setups use Redis/other pubsub to fan-out events
# across processes.
SSE_CLIENTS: set[asyncio.Queue] = set()
PENDING_SSE_EVENTS: deque[Dict[str, Any]] = deque()


async def _broadcast_sse(message: Dict[str, Any]) -> None:
    if "jsonrpc" not in message:
        logger.warning("Attempted to broadcast non JSON-RPC payload over SSE")
        return
    if not SSE_CLIENTS:
        PENDING_SSE_EVENTS.append(message)
        logger.debug("Queued JSON-RPC payload for future SSE clients: %s", message)
        return
    for q in list(SSE_CLIENTS):
        try:
            # Use put_nowait so a slow client won't block the broadcaster.
            q.put_nowait(message)
        except asyncio.QueueFull:
            # Drop message for full queues; client is likely slow.
            continue


@router.get("")
async def mcp_entrypoint(
    request: Request,
    resource_registry: ResourceRegistry = Depends(get_resource_registry),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
) -> Response:
    accept_header = request.headers.get("accept", "")
    if "text/event-stream" in accept_header.lower():
        return await mcp_sse(request)
    payload = _handshake_payload(request, resource_registry, tool_registry)
    return JSONResponse({"jsonrpc": "2.0", "method": "initialize", "params": payload})


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


@router.get("/health")
async def mcp_healthcheck() -> Dict[str, str]:
    return dict(_HEALTH_PAYLOAD)


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
            if method in {"initialized", "notifications/initialized"}:
                logger.info("Received initialized notification")
            else:
                logger.warning(f"Unknown notification method: {method}")
            return Response(status_code=204)  # No Content для notifications
        
        # Обработка метода initialize
        if method == "initialize":
            logger.info("Processing initialize request")
            result = _handshake_payload(request, resource_registry, tool_registry)
            rpc_response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
            logger.info(f"Initialize response: {rpc_response}")
            # Broadcast initialize result to any SSE-connected clients as well
            try:
                asyncio.create_task(_broadcast_sse(rpc_response))
            except Exception:
                logger.exception("Failed to broadcast initialize to SSE clients")
            return rpc_response
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
            call_result = response.to_call_tool_result()
            rpc_response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": call_result,
            }
            # Broadcast tool call result to SSE clients
            try:
                asyncio.create_task(_broadcast_sse(rpc_response))
            except Exception:
                logger.exception("Failed to broadcast tools/call to SSE clients")
            return rpc_response
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
            rpc_response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": response.model_dump(),
            }
            # Broadcast resource query result to SSE clients
            try:
                asyncio.create_task(_broadcast_sse(rpc_response))
            except Exception:
                logger.exception("Failed to broadcast resources/query to SSE clients")
            return rpc_response
        elif method == "tools/list":
            rpc_response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [tool.model_dump() for tool in tool_registry.descriptors()]
                },
            }
            try:
                asyncio.create_task(_broadcast_sse(rpc_response))
            except Exception:
                logger.exception("Failed to broadcast tools/list to SSE clients")
            return rpc_response
        elif method == "resources/list":
            rpc_response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "resources": [res.model_dump() for res in resource_registry.descriptors()]
                },
            }
            try:
                asyncio.create_task(_broadcast_sse(rpc_response))
            except Exception:
                logger.exception("Failed to broadcast resources/list to SSE clients")
            return rpc_response
        else:
            rpc_response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                },
            }
            try:
                asyncio.create_task(_broadcast_sse(rpc_response))
            except Exception:
                logger.exception("Failed to broadcast error response to SSE clients")
            return rpc_response
    else:
        # Обратная совместимость: трактуем произвольный JSON как запрос initialize
        payload = _handshake_payload(request, resource_registry, tool_registry)
        notification = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": payload,
        }
        try:
            asyncio.create_task(_broadcast_sse(notification))
        except Exception:
            logger.exception("Failed to broadcast initialize notification for legacy request")
        return notification


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
        rpc_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }
        try:
            asyncio.create_task(_broadcast_sse(rpc_response))
        except Exception:
            logger.exception("Failed to broadcast initialize to SSE clients (initialize endpoint)")
        return rpc_response
    else:
        # Обратная совместимость со старым форматом
        payload = _handshake_payload(request, resource_registry, tool_registry)
        try:
            asyncio.create_task(
                _broadcast_sse(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "result": payload,
                    }
                )
            )
        except Exception:
            logger.exception("Failed to broadcast initialize to SSE clients (initialize endpoint)")
        return {
            "jsonrpc": "2.0",
            "id": None,
            "result": payload,
        }


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
    logger.debug("resource query %s", request.model_dump())
    resp = await resource_registry.query(request)
    logger.debug(
        "resource query result resource=%s items=%d next_cursor=%s",
        resp.metadata.resource,
        len(resp.data),
        resp.next_cursor,
    )
    # Broadcast results to SSE clients
    try:
        asyncio.create_task(
            _broadcast_sse(
                {
                    "jsonrpc": "2.0",
                    "method": "resources/query",
                    "params": {"result": resp.model_dump()},
                }
            )
        )
    except Exception:
        logger.exception("Failed to broadcast resources/query from /resource/query endpoint")
    return resp


@router.post("/tool/call")
async def tool_call(
    rpc_request: Dict[str, Any] = Body(...),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
) -> Dict[str, Any]:
    """Execute a tool via MCP JSON-RPC 2.0 protocol."""

    logger.debug("tool call request payload: %s", rpc_request)
    
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
        logger.debug("tool call details jsonrpc_id=%s method=%s tool=%s params=%s", request_id, method, tool_name, tool_params)
        
        tool_request = ToolCallRequest(tool=tool_name, params=tool_params)
        response = await tool_registry.call(tool_request)
        call_result = response.to_call_tool_result()
        logger.debug("tool call %s finished warnings=%s pagination=%s", tool_name, bool(response.warnings), response.structuredContent.get("pagination") if isinstance(response.structuredContent, dict) else None)
        rpc_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": call_result,
        }

        # Also broadcast tool result to SSE clients
        try:
            asyncio.create_task(_broadcast_sse(rpc_response))
        except Exception:
            logger.exception("Failed to broadcast tools/call from /tool/call endpoint")

        return rpc_response
    else:
        # Старый формат для обратной совместимости
        logger.debug("tool call legacy format request: %s", rpc_request)
        tool_request = ToolCallRequest(**rpc_request)
        response = await tool_registry.call(tool_request)
        call_result = response.to_call_tool_result()
        rpc_notification = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"result": call_result},
        }
        try:
            asyncio.create_task(_broadcast_sse(rpc_notification))
        except Exception:
            logger.exception("Failed to broadcast tools/call (legacy format) to SSE clients")
        return call_result


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
                await websocket.send_text(_json_dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}))
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
                    await websocket.send_text(_json_dumps(response))

                elif method == "tools/list":
                    await websocket.send_text(_json_dumps({"jsonrpc": "2.0", "id": request_id, "result": {"tools": [t.model_dump() for t in tool_registry.descriptors()]}}))

                elif method == "resources/list":
                    await websocket.send_text(_json_dumps({"jsonrpc": "2.0", "id": request_id, "result": {"resources": [r.model_dump() for r in resource_registry.descriptors()]}}))

                elif method == "tools/call":
                    tool_name = params.get("name")
                    tool_params = params.get("arguments", {})
                    if not tool_name:
                        await websocket.send_text(_json_dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Invalid params: tool name required"}}))
                        continue
                    tool_request = ToolCallRequest(tool=tool_name, params=tool_params)
                    resp = await tool_registry.call(tool_request)
                    await websocket.send_text(_json_dumps({"jsonrpc": "2.0", "id": request_id, "result": resp.to_call_tool_result()}))

                elif method == "resources/query":
                    resource_name = params.get("uri")
                    resource_params = params.get("arguments", {})
                    cursor = params.get("cursor")
                    if not resource_name:
                        await websocket.send_text(_json_dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Invalid params: resource uri required"}}))
                        continue
                    resource_request = ResourceQueryRequest(resource=resource_name, params=resource_params, cursor=cursor)
                    resp = await resource_registry.query(resource_request)
                    await websocket.send_text(_json_dumps({"jsonrpc": "2.0", "id": request_id, "result": resp.model_dump()}))

                else:
                    await websocket.send_text(_json_dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}))

            else:
                # Back-compat: send handshake payload if not a JSON-RPC body
                payload = _handshake_payload(websocket, resource_registry, tool_registry)
                await websocket.send_text(_json_dumps({"jsonrpc": "2.0", "method": "initialize", "params": payload}))

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
        try:
            yield "event: endpoint\ndata: /mcp\n\n"
        except Exception:
            logger.exception("Failed to advertise SSE endpoint path")

        try:
            while PENDING_SSE_EVENTS:
                pending = PENDING_SSE_EVENTS.popleft()
                try:
                    yield "event: message\ndata: " + _json_dumps(pending) + "\n\n"
                except Exception:
                    logger.exception("Failed to serialize pending SSE payload")
                    continue
        except Exception:
            logger.exception("Failed to flush pending SSE payloads")

        try:
            while True:
                try:
                    item = await q.get()
                except asyncio.CancelledError:
                    break
                try:
                    yield "event: message\n" + f"data: {_json_dumps(item)}\n\n"
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
