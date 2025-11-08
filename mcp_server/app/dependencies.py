from __future__ import annotations

from fastapi import Request

from .mcp.resources import ResourceRegistry
from .mcp.tools import ToolRegistry


def get_resource_registry(request: Request) -> ResourceRegistry:
    registry = getattr(request.app.state, "resource_registry", None)
    if registry is None:  # pragma: no cover - defensive
        raise RuntimeError("Resource registry is not configured")
    return registry


def get_tool_registry(request: Request) -> ToolRegistry:
    registry = getattr(request.app.state, "tool_registry", None)
    if registry is None:  # pragma: no cover - defensive
        raise RuntimeError("Tool registry is not configured")
    return registry
