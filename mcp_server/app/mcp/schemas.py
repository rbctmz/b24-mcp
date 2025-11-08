from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class MCPMetadata(BaseModel):
    """Generic metadata returned with MCP responses."""

    provider: Literal["bitrix24"]
    resource: Optional[str] = None
    tool: Optional[str] = None
    instance_name: Optional[str] = Field(default=None, description="Logical Bitrix24 instance name")


class ResourceDescriptor(BaseModel):
    uri: str
    name: Optional[str] = None
    description: Optional[str] = None


class ToolDescriptor(BaseModel):
    name: str
    description: Optional[str] = None
    inputSchema: Dict[str, Any] = Field(default_factory=dict, description="JSON schema specifying accepted parameters")


class MCPIndexResponse(BaseModel):
    """Response model for MCP discovery endpoint."""

    resources: List[ResourceDescriptor]
    tools: List[ToolDescriptor]




class ResourceQueryRequest(BaseModel):
    resource: str
    params: Dict[str, Any] = Field(default_factory=dict)
    cursor: Optional[str] = None


class ResourceQueryResponse(BaseModel):
    metadata: MCPMetadata
    data: List[Dict[str, Any]]
    next_cursor: Optional[str] = None


class ToolCallRequest(BaseModel):
    tool: str
    params: Dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    metadata: MCPMetadata
    result: Dict[str, Any]
