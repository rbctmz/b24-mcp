from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException, status


class MCPError(HTTPException):
    """Base error for MCP-specific failures."""

    def __init__(self, detail: Any, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        super().__init__(status_code=status_code, detail=detail)


class ResourceNotFoundError(MCPError):
    def __init__(self, resource: str) -> None:
        super().__init__(
            {"type": "resource_not_found", "message": f"Resource '{resource}' is not registered."},
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ToolNotFoundError(MCPError):
    def __init__(self, tool: str) -> None:
        super().__init__(
            {"type": "tool_not_found", "message": f"Tool '{tool}' is not registered."},
            status_code=status.HTTP_404_NOT_FOUND,
        )


class UpstreamError(MCPError):
    def __init__(self, *, message: str, status_code: int = status.HTTP_502_BAD_GATEWAY, payload: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            {
                "type": "upstream_error",
                "message": message,
                "payload": payload or {},
            },
            status_code=status_code,
        )
