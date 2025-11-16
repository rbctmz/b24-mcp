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
    total: Optional[int] = None


class ToolCallRequest(BaseModel):
    tool: str
    params: Dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    metadata: MCPMetadata
    result: Dict[str, Any]
    structuredContent: Optional[Dict[str, Any]] = None
    content: Optional[List[Dict[str, Any]]] = None
    warnings: Optional[List[Dict[str, Any]]] = None
    is_error: bool = False

    def model_dump(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(*args, **kwargs)

    def to_call_tool_result(self) -> Dict[str, Any]:
        if self.structuredContent is not None:
            structured_payload = self.structuredContent
        else:
            structured_payload = {
                "metadata": self.metadata.model_dump(exclude_none=True),
                "result": self.result,
            }
            if self.warnings:
                structured_payload["warnings"] = self.warnings

        if self.content is not None:
            content_payload = self.content
        else:
            items_count: Optional[int] = None
            if isinstance(self.result, dict):
                payload_items = self.result.get("result")
                if isinstance(payload_items, list):
                    items_count = len(payload_items)

            resource_name = self.metadata.resource or self.metadata.tool or "Bitrix24"
            if items_count is not None:
                summary_text = (
                    f"{resource_name}: получено {items_count} записей. Полный ответ в structuredContent.result."
                )
            else:
                summary_text = f"{resource_name}: ответ получен. Полный результат в structuredContent.result."
            content_payload = [
                {
                    "type": "text",
                    "text": summary_text,
                }
            ]
            if self.warnings:
                for warning in self.warnings:
                    message = warning.get("message") if isinstance(warning, dict) else str(warning)
                    appendix = ""
                    if isinstance(warning, dict) and warning.get("suggested_filters"):
                        appendix = f" Рекомендуемые фильтры: {warning['suggested_filters']}"
                    content_payload.append({"type": "text", "text": f"⚠️ {message}{appendix}"})

        return {
            "content": content_payload,
            "structuredContent": structured_payload,
            "isError": self.is_error,
        }
