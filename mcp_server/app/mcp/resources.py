from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional
import copy

from ..bitrix_client import BitrixAPIError, BitrixClient
from ..exceptions import ResourceNotFoundError, UpstreamError
from ..settings import BitrixSettings
from .schemas import MCPMetadata, ResourceDescriptor, ResourceQueryRequest, ResourceQueryResponse
from ..prompt_loader import get_resource_docs

ResourceHandler = Callable[[BitrixClient, Dict[str, Any], Optional[str]], Awaitable[ResourceQueryResponse]]

_DEFAULT_LOCALE = "ru"

_RESOURCE_DEFAULTS: Dict[str, Dict[str, str]] = {
    "crm/deals": {
        "name": "CRM Deals",
        "description": "Список сделок с фильтрами (crm.deal.list).",
    },
    "crm/leads": {
        "name": "CRM Leads",
        "description": "Список лидов с фильтрами (crm.lead.list).",
    },
    "crm/contacts": {
        "name": "CRM Contacts",
        "description": "Список контактов (crm.contact.list).",
    },
    "crm/users": {
        "name": "Portal Users",
        "description": "Список пользователей портала (user.get).",
    },
    "crm/tasks": {
        "name": "Tasks",
        "description": "Список задач (tasks.task.list).",
    },
    "bitrix24_leads_guide": {
        "name": "Шпаргалка по лидам",
        "description": "Готовые payload'ы для crm.lead.list.",
    },
}


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
        self._locale = _DEFAULT_LOCALE
        self._resource_docs = get_resource_docs(self._locale)
        self._registry: Dict[str, ResourceHandler] = {
            "crm/deals": self._deals_handler,
            "crm/leads": self._leads_handler,
            "crm/contacts": self._contacts_handler,
            "crm/users": self._users_handler,
            "crm/tasks": self._tasks_handler,
            "bitrix24_leads_guide": self._leads_guide_handler,
        }
        self._descriptors: Dict[str, ResourceDescriptor] = {}
        for uri in self._registry.keys():
            descriptor_data = self._resource_docs.get(uri, {})
            nested_descriptor = descriptor_data.get("descriptor")
            if isinstance(nested_descriptor, dict):
                descriptor_source = nested_descriptor
            else:
                descriptor_source = descriptor_data if isinstance(descriptor_data, dict) else {}
            name = descriptor_source.get("name") or _RESOURCE_DEFAULTS.get(uri, {}).get("name") or uri
            description = descriptor_source.get("description") or _RESOURCE_DEFAULTS.get(uri, {}).get("description")
            self._descriptors[uri] = ResourceDescriptor(uri=uri, name=name, description=description)

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

    async def _leads_guide_handler(
        self,
        client: BitrixClient,
        params: Dict[str, Any],
        cursor: Optional[str],
    ) -> ResourceQueryResponse:
        guide_doc = self._resource_docs.get("bitrix24_leads_guide", {})
        scenarios_source = guide_doc.get("scenarios", [])
        if isinstance(scenarios_source, list):
            scenarios_raw = copy.deepcopy(scenarios_source)
        else:
            scenarios_raw = []

        title_filter: Optional[str] = None
        if isinstance(params, dict):
            filter_value = params.get("title") or params.get("scenario")
            if isinstance(filter_value, str):
                title_filter = filter_value.lower()

        scenarios: List[Dict[str, Any]] = []
        for scenario in scenarios_raw:
            if not isinstance(scenario, dict):
                continue
            title = str(scenario.get("title", ""))
            if title_filter and title_filter not in title.lower():
                continue
            scenarios.append(
                {
                    "type": "scenario",
                    "title": title,
                    "description": scenario.get("description"),
                    "payload": scenario.get("payload"),
                }
            )

        rules_source = guide_doc.get("rules", [])
        if isinstance(rules_source, list) and rules_source:
            scenarios.append(
                {
                    "type": "rules",
                    "rules": list(rules_source),
                }
            )

        metadata = _metadata("bitrix24_leads_guide", client.settings)
        return ResourceQueryResponse(metadata=metadata, data=scenarios, next_cursor=None)
