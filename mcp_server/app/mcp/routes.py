from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Request

from ..dependencies import get_resource_registry, get_tool_registry
from ..mcp.resources import ResourceRegistry
from ..mcp.tools import ToolRegistry
from .schemas import MCPIndexResponse, ResourceQueryRequest, ResourceQueryResponse, ToolCallRequest, ToolCallResponse

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
    request: Request,
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


@router.get("")
async def mcp_healthcheck() -> Dict[str, str]:
    return dict(_HEALTH_PAYLOAD)


@router.options("")
async def mcp_options() -> Dict[str, str]:
    return dict(_HEALTH_PAYLOAD)


@router.post("")
async def mcp_handshake(
    request: Request,
    resource_registry: ResourceRegistry = Depends(get_resource_registry),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
) -> Dict[str, Any]:
    """Handle MCP JSON-RPC 2.0 requests including initialize."""
    
    # Попытка прочитать тело запроса разными способами
    try:
        body = await request.json()
    except Exception:
        # Если не удалось распарсить как JSON, пытаемся прочитать как строку
        try:
            body_bytes = await request.body()
            if not body_bytes:
                # Пустое тело - возвращаем ошибку JSON-RPC
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
        except Exception as e:
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
        
        # Обработка метода initialize
        if method == "initialize":
            result = _handshake_payload(request, resource_registry, tool_registry)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }
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
        # Не JSON-RPC формат - возвращаем ошибку
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32600,
                "message": "Invalid Request: not a valid JSON-RPC 2.0 request"
            }
        }


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
        return _handshake_payload(request, resource_registry, tool_registry)


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
    return await resource_registry.query(request)


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
