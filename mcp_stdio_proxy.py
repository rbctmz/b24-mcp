#!/usr/bin/env python3
"""
stdio <-> HTTP proxy for Bitrix24 MCP server.
Bridges Claude Desktop (stdio) to FastAPI MCP server (HTTP).
"""
import sys
import json
import httpx
import asyncio
from typing import Dict, Any

BASE_URL = "http://127.0.0.1:8000"

async def handle_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Forward JSON-RPC request to HTTP MCP server."""
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")
    
    try:
        async with httpx.AsyncClient() as client:
            if method == "initialize":
                # Handle initialize
                response = await client.get(f"{BASE_URL}/mcp/index")
                result = response.json()
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "serverInfo": {
                            "name": "bitrix24-mcp",
                            "version": "1.0.0"
                        }
                    }
                }
            
            elif method == "resources/list":
                response = await client.get(f"{BASE_URL}/mcp/index")
                data = response.json()
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"resources": data.get("resources", [])}
                }
            
            elif method == "resources/read":
                uri = params.get("uri", "")
                response = await client.post(
                    f"{BASE_URL}/mcp/resource/query",
                    json={"resource": uri, "params": params}
                )
                data = response.json()
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(data)}]}
                }
            
            elif method == "tools/list":
                response = await client.get(f"{BASE_URL}/mcp/index")
                data = response.json()
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": data.get("tools", [])}
                }
            
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_params = params.get("arguments", {})
                response = await client.post(
                    f"{BASE_URL}/mcp/tool/call",
                    json={"tool": tool_name, "params": tool_params}
                )
                data = response.json()
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(data)}]}
                }
            
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }
    
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32603, "message": str(e)}
        }

async def main():
    """Read JSON-RPC from stdin, forward to HTTP server, write to stdout."""
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line.strip())
                response = await handle_request(request)
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
            except json.JSONDecodeError:
                continue
            except BrokenPipeError:
                # Client closed connection, exit gracefully
                break
            except Exception as e:
                # Don't crash on other errors, just continue
                continue
    except BrokenPipeError:
        # Exit gracefully if pipe is broken
        pass

if __name__ == "__main__":
    asyncio.run(main())