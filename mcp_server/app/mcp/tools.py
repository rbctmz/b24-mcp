from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
import logging

from ..bitrix_client import BitrixAPIError, BitrixClient
from ..exceptions import ToolNotFoundError, UpstreamError
from ..settings import BitrixSettings
from .schemas import MCPMetadata, ToolCallRequest, ToolCallResponse, ToolDescriptor

ToolHandler = Callable[[BitrixClient, Dict[str, Any]], Awaitable[ToolCallResponse]]

logger = logging.getLogger(__name__)


def _metadata(tool: str, settings: BitrixSettings, resource: Optional[str] = None) -> MCPMetadata:
    return MCPMetadata(provider="bitrix24", tool=tool, resource=resource, instance_name=settings.instance_name)


async def _call_bitrix(
    client: BitrixClient,
    *,
    tool: str,
    method: str,
    payload: Dict[str, Any],
    resource: Optional[str] = None,
) -> ToolCallResponse:
    try:
        response = await client.call_method(method, payload)
    except BitrixAPIError as exc:  # pragma: no cover - simple passthrough
        raise UpstreamError(message=str(exc), payload=exc.payload, status_code=502) from exc

    return ToolCallResponse(
        metadata=_metadata(tool, client.settings, resource=resource),
        result=response,
    )


class ToolRegistry:
    """Registers and resolves MCP tools."""

    def __init__(self, client: BitrixClient) -> None:
        self._client = client

        self._registry: Dict[str, ToolHandler] = {
            "getDeals": self._get_deals,
            "getLeads": self._get_leads,
            "getContacts": self._get_contacts,
            "getUsers": self._get_users,
            "getTasks": self._get_tasks,
        }

        self._descriptors: Dict[str, ToolDescriptor] = {
            "getDeals": ToolDescriptor(
                name="getDeals",
                description="Fetch deals using crm.deal.list with optional filters.",
                inputSchema=_list_args_schema(),
            ),
            "getLeads": ToolDescriptor(
                name="getLeads",
                description="Fetch leads using crm.lead.list with optional filters.",
                inputSchema=_list_args_schema(),
            ),
            "getContacts": ToolDescriptor(
                name="getContacts",
                description="Fetch contacts using crm.contact.list with optional filters.",
                inputSchema=_list_args_schema(),
            ),
            "getUsers": ToolDescriptor(
                name="getUsers",
                description="Fetch users using user.get.",
                inputSchema=_list_args_schema(),
            ),
            "getTasks": ToolDescriptor(
                name="getTasks",
                description="Fetch tasks using tasks.task.list.",
                inputSchema=_list_args_schema(),
            ),
        }

    def descriptors(self) -> List[ToolDescriptor]:
        return list(self._descriptors.values())

    async def call(self, request: ToolCallRequest) -> ToolCallResponse:
        handler = self._registry.get(request.tool)
        if handler is None:
            raise ToolNotFoundError(request.tool)
        return await handler(self._client, request.params)

    async def _get_deals(self, client: BitrixClient, params: Dict[str, Any]) -> ToolCallResponse:
        return await _call_bitrix(
            client,
            tool="getDeals",
            resource="crm/deals",
            method="crm.deal.list",
            payload=params,
        )

    async def _get_leads(self, client: BitrixClient, params: Dict[str, Any]) -> ToolCallResponse:
        payload = dict(params)
        logger.info(f"[getLeads] Input params: {params}")

        # Разбор и валидация параметра limit до использования
        requested_limit: Optional[int] = None
        if "limit" in params and params.get("limit") is not None:
            try:
                requested_limit = int(params.get("limit"))
            except (ValueError, TypeError) as e:
                logger.warning(f"[getLeads] Invalid limit value: {params.get('limit')}, error: {e}")
                requested_limit = None

        if requested_limit is not None:
            # enforce server-side cap
            cap = 500
            payload["limit"] = requested_limit if requested_limit <= cap else cap
            logger.info(f"[getLeads] Setting limit in payload: {payload['limit']}")
        else:
            logger.info("[getLeads] No valid limit specified in params; not setting limit")

        logger.info(f"[getLeads] Final payload to Bitrix24: {payload}")

        response = await _call_bitrix(
            client,
            tool="getLeads",
            resource="crm/leads",
            method="crm.lead.list",
            payload=payload,
        )

        # Проверяем результат
        result = response.result
        if isinstance(result, dict) and "result" in result:
            leads_list = result["result"]
            if isinstance(leads_list, list):
                returned_count = len(leads_list)
                logger.info(f"[getLeads] Bitrix24 returned {returned_count} leads")

                # Обрезаем, если нужно
                if requested_limit is not None and requested_limit > 0 and returned_count > requested_limit:
                    logger.warning(f"[getLeads] Truncating from {returned_count} to {requested_limit}")
                    result["result"] = leads_list[:requested_limit]
                    # Обновляем счетчик
                    result["total"] = min(result.get("total", returned_count), requested_limit)

        return response

    async def _get_contacts(self, client: BitrixClient, params: Dict[str, Any]) -> ToolCallResponse:
        return await _call_bitrix(
            client,
            tool="getContacts",
            resource="crm/contacts",
            method="crm.contact.list",
            payload=params,
        )

    async def _get_users(self, client: BitrixClient, params: Dict[str, Any]) -> ToolCallResponse:
        return await _call_bitrix(
            client,
            tool="getUsers",
            resource="crm/users",
            method="user.get",
            payload=params,
        )

    async def _get_tasks(self, client: BitrixClient, params: Dict[str, Any]) -> ToolCallResponse:
        return await _call_bitrix(
            client,
            tool="getTasks",
            resource="crm/tasks",
            method="tasks.task.list",
            payload=params,
        )


def _list_args_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "select": {"type": ["array", "null"], "items": {"type": "string"}},
            "filter": {"type": ["object", "null"]},
            "order": {"type": ["object", "null"]},
            "start": {"type": ["integer", "null"], "minimum": 0},
            "limit": {"type": ["integer", "null"], "minimum": 1},
        },
    }
