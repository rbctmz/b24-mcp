from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional

from ..bitrix_client import BitrixAPIError, BitrixClient
from ..exceptions import ResourceNotFoundError, UpstreamError
from ..settings import BitrixSettings
from .schemas import MCPMetadata, ResourceDescriptor, ResourceQueryRequest, ResourceQueryResponse

ResourceHandler = Callable[[BitrixClient, Dict[str, Any], Optional[str]], Awaitable[ResourceQueryResponse]]


def _metadata(resource: str, settings: BitrixSettings) -> MCPMetadata:
    return MCPMetadata(provider="bitrix24", resource=resource, instance_name=settings.instance_name)


def _prepare_payload(params: Dict[str, Any], cursor: Optional[str]) -> Dict[str, Any]:
    payload = dict(params)
    if cursor is not None:
        payload["start"] = int(cursor)
    return payload


async def _list_entities(
    client: BitrixClient,
    *,
    resource: str,
    method: str,
    params: Dict[str, Any],
    cursor: Optional[str],
) -> ResourceQueryResponse:
    payload = _prepare_payload(params, cursor)

    try:
        response = await client.call_method(method, payload)
    except BitrixAPIError as exc:  # pragma: no cover - simple passthrough
        raise UpstreamError(message=str(exc), payload=exc.payload, status_code=502) from exc

    data = response.get("result") or []
    next_cursor = response.get("next")
    metadata = _metadata(resource, client.settings)

    return ResourceQueryResponse(
        metadata=metadata,
        data=data,
        next_cursor=str(next_cursor) if next_cursor is not None else None,
    )


class ResourceRegistry:
    """Registers and resolves MCP resources."""

    def __init__(self, client: BitrixClient) -> None:
        self._client = client
        self._registry: Dict[str, ResourceHandler] = {
            "crm/deals": self._deals_handler,
            "crm/leads": self._leads_handler,
            "crm/contacts": self._contacts_handler,
            "crm/users": self._users_handler,
            "crm/tasks": self._tasks_handler,
        }
        self._descriptors: Dict[str, ResourceDescriptor] = {
            "crm/deals": ResourceDescriptor(
                uri="crm/deals",
                name="CRM Deals",
                description="List CRM deals with optional filters (crm.deal.list)",
            ),
            "crm/leads": ResourceDescriptor(
                uri="crm/leads",
                name="CRM Leads",
                description="List CRM leads with optional filters (crm.lead.list)",
            ),
            "crm/contacts": ResourceDescriptor(
                uri="crm/contacts",
                name="CRM Contacts",
                description="List CRM contacts with optional filters (crm.contact.list)",
            ),
            "crm/users": ResourceDescriptor(
                uri="crm/users",
                name="Portal Users",
                description="List portal users (user.get)",
            ),
            "crm/tasks": ResourceDescriptor(
                uri="crm/tasks",
                name="Tasks",
                description="List tasks with optional filters (tasks.task.list)",
            ),
        }

    def descriptors(self) -> List[ResourceDescriptor]:
        return list(self._descriptors.values())

    async def query(self, request: ResourceQueryRequest) -> ResourceQueryResponse:
        handler = self._registry.get(request.resource)
        if handler is None:
            raise ResourceNotFoundError(request.resource)
        return await handler(self._client, request.params, request.cursor)

    async def _deals_handler(self, client: BitrixClient, params: Dict[str, Any], cursor: Optional[str]) -> ResourceQueryResponse:
        return await _list_entities(
            client,
            resource="crm/deals",
            method="crm.deal.list",
            params=params,
            cursor=cursor,
        )

    async def _leads_handler(self, client: BitrixClient, params: Dict[str, Any], cursor: Optional[str]) -> ResourceQueryResponse:
        return await _list_entities(
            client,
            resource="crm/leads",
            method="crm.lead.list",
            params=params,
            cursor=cursor,
        )

    async def _contacts_handler(self, client: BitrixClient, params: Dict[str, Any], cursor: Optional[str]) -> ResourceQueryResponse:
        return await _list_entities(
            client,
            resource="crm/contacts",
            method="crm.contact.list",
            params=params,
            cursor=cursor,
        )

    async def _users_handler(self, client: BitrixClient, params: Dict[str, Any], cursor: Optional[str]) -> ResourceQueryResponse:
        return await _list_entities(
            client,
            resource="crm/users",
            method="user.get",
            params=params,
            cursor=cursor,
        )

    async def _tasks_handler(self, client: BitrixClient, params: Dict[str, Any], cursor: Optional[str]) -> ResourceQueryResponse:
        return await _list_entities(
            client,
            resource="crm/tasks",
            method="tasks.task.list",
            params=params,
            cursor=cursor,
        )
