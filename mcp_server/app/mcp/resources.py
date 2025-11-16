from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Set
import copy
import json
import time

from ..bitrix_client import BitrixAPIError, BitrixClient
from ..exceptions import ResourceNotFoundError, UpstreamError
from ..settings import BitrixSettings
from .schemas import MCPMetadata, ResourceDescriptor, ResourceQueryRequest, ResourceQueryResponse
from ..prompt_loader import get_resource_docs

ResourceHandler = Callable[[BitrixClient, Dict[str, Any], Optional[str]], Awaitable[ResourceQueryResponse]]

_DEFAULT_LOCALE = "ru"
_CACHE_TTL_SECONDS = 300

_SEMANTIC_GROUP_LABELS: Dict[str, str] = {
    "process": "В работе",
    "success": "Заключена",
    "failure": "Провалена",
}

_RESOURCE_DEFAULTS: Dict[str, Dict[str, str]] = {
    "crm/deals": {
        "name": "CRM Deals",
        "description": "Список сделок с фильтрами (crm.deal.list).",
    },
    "crm/lead_statuses": {
        "name": "CRM Lead Stages",
        "description": "Справочник стадий лидов (crm.status.list с ENTITY_ID=STATUS).",
    },
    "crm/leads": {
        "name": "CRM Leads",
        "description": "Список лидов с фильтрами (crm.lead.list).",
    },
    "crm/deal_stages": {
        "name": "CRM Deal Stages",
        "description": "Справочник стадий сделок по направлениям (crm.dealcategory.stage.list).",
    },
    "crm/deal_categories": {
        "name": "CRM Deal Categories",
        "description": "Справочник воронок сделок (crm.dealcategory.list).",
    },
    "crm/lead_sources": {
        "name": "CRM Lead Sources",
        "description": "Справочник источников лидов (crm.status.list с ENTITY_ID=SOURCE).",
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
    "tasks/statuses": {
        "name": "Task Statuses",
        "description": "Справочник статусов задач (tasks.task.getFields -> STATUS).",
    },
    "tasks/priorities": {
        "name": "Task Priorities",
        "description": "Справочник приоритетов задач (tasks.task.getFields -> PRIORITY).",
    },
    "bitrix24_leads_guide": {
        "name": "Шпаргалка по лидам",
        "description": "Готовые payload'ы для crm.lead.list.",
    },
    "crm/currencies": {
        "name": "CRM Currencies",
        "description": "Справочник валют (crm.currency.list).",
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
    total_value = response.get("total")
    if isinstance(total_value, str):
        try:
            total = int(total_value)
        except ValueError:
            total = None
    elif isinstance(total_value, int):
        total = total_value
    else:
        total = None
    metadata = _metadata(resource, client.settings)

    return ResourceQueryResponse(
        metadata=metadata,
        data=data,
        next_cursor=str(next_cursor) if next_cursor is not None else None,
        total=total,
    )


def _normalize_enum_items(field_definition: Any) -> List[Dict[str, Any]]:
    """Extract enumeration items from Bitrix field descriptors."""

    items: List[Dict[str, Any]] = []
    if isinstance(field_definition, dict):
        for key in ("ENUM", "enum", "ITEMS", "items", "VALUES", "values"):
            enum_items = field_definition.get(key)
            if isinstance(enum_items, list):
                items = enum_items
                break
            if isinstance(enum_items, dict):
                normalized: List[Dict[str, Any]] = []
                for enum_key, enum_value in enum_items.items():
                    if isinstance(enum_value, dict):
                        item = {"ID": str(enum_key)}
                        item.update(enum_value)
                    else:
                        item = {"ID": str(enum_key), "NAME": enum_value}
                    normalized.append(item)
                items = normalized
                break
        if not items:
            labels = field_definition.get("LABELS") or field_definition.get("labels")
            if isinstance(labels, dict):
                items = [{"ID": str(key), "NAME": value} for key, value in labels.items()]
        if not items:
            values = field_definition.get("VALUE") or field_definition.get("value")
            if isinstance(values, list):
                items = values
    elif isinstance(field_definition, list):
        items = field_definition
    return items


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _index_by_keys(items: Iterable[Dict[str, Any]], keys: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in keys:
            if key in item and item[key] is not None:
                identifier = _safe_str(item[key])
                if identifier:
                    index[identifier] = item
                    break
    return index


def _ensure_meta(record: Dict[str, Any]) -> Dict[str, Any]:
    meta = record.get("_meta")
    if not isinstance(meta, dict):
        meta = {}
        record["_meta"] = meta
    return meta


def _user_display_name(user: Dict[str, Any]) -> str:
    parts = [
        str(user.get("NAME") or "").strip(),
        str(user.get("LAST_NAME") or "").strip(),
    ]
    filtered = [part for part in parts if part]
    if filtered:
        return " ".join(filtered)
    if user.get("LOGIN"):
        return str(user["LOGIN"])
    return str(user.get("ID") or "unknown")


def _build_user_summary(user_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": user_id,
        "name": _user_display_name(user),
        "firstName": user.get("NAME"),
        "lastName": user.get("LAST_NAME"),
        "email": user.get("EMAIL"),
        "workPosition": user.get("WORK_POSITION"),
        "raw": copy.deepcopy(user),
    }


def _extract_semantics(entry: Dict[str, Any]) -> Optional[str]:
    if not isinstance(entry, dict):
        return None
    semantics = entry.get("SEMANTICS") or entry.get("STATUS")
    if semantics:
        return str(semantics)
    extra = entry.get("EXTRA")
    if isinstance(extra, dict):
        return extra.get("SEMANTICS")
    return None


def _semantic_group_label(semantics: Optional[str]) -> Optional[str]:
    if not semantics:
        return None
    return _SEMANTIC_GROUP_LABELS.get(semantics.lower(), semantics)


def _build_enum_summary(entry_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": entry_id,
        "name": entry.get("NAME") or entry.get("TITLE") or entry.get("VALUE"),
        "raw": copy.deepcopy(entry),
    }


class ResourceRegistry:
    """Registers and resolves MCP resources."""

    def __init__(self, client: BitrixClient) -> None:
        self._client = client
        self._locale = _DEFAULT_LOCALE
        self._resource_docs = get_resource_docs(self._locale)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._user_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._registry: Dict[str, ResourceHandler] = {
            "crm/deals": self._deals_handler,
            "crm/lead_statuses": self._lead_statuses_handler,
            "crm/lead_sources": self._lead_sources_handler,
            "crm/leads": self._leads_handler,
            "crm/currencies": self._currencies_handler,
            "crm/deal_categories": self._deal_categories_handler,
            "crm/deal_stages": self._deal_stages_handler,
            "crm/contacts": self._contacts_handler,
            "crm/users": self._users_handler,
            "crm/tasks": self._tasks_handler,
            "tasks/statuses": self._task_statuses_handler,
            "tasks/priorities": self._task_priorities_handler,
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
        response = await _list_entities(
            client,
            resource="crm/deals",
            method="crm.deal.list",
            params=params,
            cursor=cursor,
        )
        response.data = await self._enrich_deals(client, response.data)
        return response

    async def _cacheable_query(
        self,
        *,
        resource: str,
        params: Dict[str, Any],
        cursor: Optional[str],
        fetcher: Callable[[], Awaitable[ResourceQueryResponse]],
    ) -> ResourceQueryResponse:
        if cursor is not None:
            return await fetcher()

        cache_key = self._build_cache_key(resource, params)
        cached = self._cache.get(cache_key)
        now = time.monotonic()
        if cached and now - cached["ts"] <= _CACHE_TTL_SECONDS:
            metadata = _metadata(resource, self._client.settings)
            return ResourceQueryResponse(
                metadata=metadata,
                data=copy.deepcopy(cached["data"]),
                next_cursor=cached["next_cursor"],
            )

        response = await fetcher()
        self._cache[cache_key] = {
            "ts": now,
            "data": copy.deepcopy(response.data),
            "next_cursor": response.next_cursor,
        }
        return response

    def _build_cache_key(self, resource: str, params: Dict[str, Any]) -> str:
        if not params:
            return f"{resource}::{{}}"
        try:
            params_blob = json.dumps(params, sort_keys=True, ensure_ascii=False)
        except TypeError:
            params_blob = repr(sorted(params.items()))
        return f"{resource}::{params_blob}"

    async def _load_users(self, client: BitrixClient, user_ids: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
        normalized_ids: Set[str] = set()
        for user_id in user_ids:
            key = _safe_str(user_id)
            if key:
                normalized_ids.add(key)

        result: Dict[str, Dict[str, Any]] = {}
        missing: List[str] = []
        # TODO: Consider batching user lookups via Bitrix batch API or persisting cache across runs for large portals.
        for user_id in normalized_ids:
            if user_id in self._user_cache:
                cached = self._user_cache[user_id]
                if isinstance(cached, dict):
                    result[user_id] = cached
                continue
            missing.append(user_id)

        for user_id in missing:
            payload_id: Any
            try:
                payload_id = int(user_id)
            except ValueError:
                payload_id = user_id
            try:
                response = await client.call_method("user.get", {"ID": payload_id})
            except BitrixAPIError:
                self._user_cache[user_id] = None
                continue

            user_payload = response.get("result")
            user_data: Optional[Dict[str, Any]] = None
            if isinstance(user_payload, dict):
                user_data = user_payload
            elif isinstance(user_payload, list):
                for entry in user_payload:
                    if isinstance(entry, dict):
                        user_data = entry
                        break

            if not isinstance(user_data, dict):
                self._user_cache[user_id] = None
                continue

            resolved_id = _safe_str(user_data.get("ID")) or user_id
            self._user_cache[user_id] = user_data
            if resolved_id != user_id:
                self._user_cache[resolved_id] = user_data
            result[user_id] = user_data
            if resolved_id != user_id:
                result[resolved_id] = user_data

        for user_id in normalized_ids:
            cached = self._user_cache.get(user_id)
            if isinstance(cached, dict):
                result[user_id] = cached

        return result

    async def _enrich_leads(self, client: BitrixClient, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not items:
            return items

        enriched: List[Dict[str, Any]] = [copy.deepcopy(item) for item in items]

        user_ids: Set[str] = set()
        for item in items:
            for key in ("ASSIGNED_BY_ID", "CREATED_BY_ID", "MODIFY_BY_ID"):
                value = _safe_str(item.get(key))
                if value:
                    user_ids.add(value)
        users = await self._load_users(client, user_ids)

        status_response = await self._status_dictionary_handler(
            client,
            params={},
            cursor=None,
            resource="crm/lead_statuses",
            entity_id="STATUS",
        )
        status_map = _index_by_keys(status_response.data, ("STATUS_ID", "ID"))

        source_response = await self._status_dictionary_handler(
            client,
            params={},
            cursor=None,
            resource="crm/lead_sources",
            entity_id="SOURCE",
        )
        source_map = _index_by_keys(source_response.data, ("ID", "SOURCE_ID", "STATUS_ID"))

        currency_response = await self._currencies_handler(client, params={}, cursor=None)
        currency_map = _index_by_keys(currency_response.data, ("CURRENCY", "ID", "CODE"))

        for item in enriched:
            meta = _ensure_meta(item)
            assigned_key = _safe_str(item.get("ASSIGNED_BY_ID"))
            if assigned_key and assigned_key in users:
                meta["responsible"] = _build_user_summary(assigned_key, users[assigned_key])

            creator_key = _safe_str(item.get("CREATED_BY_ID"))
            if creator_key and creator_key in users:
                meta["creator"] = _build_user_summary(creator_key, users[creator_key])

            modifier_key = _safe_str(item.get("MODIFY_BY_ID"))
            if modifier_key and modifier_key in users:
                meta["modifier"] = _build_user_summary(modifier_key, users[modifier_key])

            status_key = _safe_str(item.get("STATUS_ID"))
            if status_key and status_key in status_map:
                meta["status"] = _build_enum_summary(status_key, status_map[status_key])

            source_key = _safe_str(item.get("SOURCE_ID"))
            if source_key and source_key in source_map:
                meta["source"] = _build_enum_summary(source_key, source_map[source_key])

            currency_key = _safe_str(item.get("CURRENCY_ID")) or _safe_str(item.get("CURRENCY"))
            if currency_key and currency_key in currency_map:
                meta["currency"] = _build_enum_summary(currency_key, currency_map[currency_key])

        return enriched

    async def _enrich_deals(self, client: BitrixClient, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not items:
            return items

        enriched: List[Dict[str, Any]] = [copy.deepcopy(item) for item in items]

        user_ids = {_safe_str(item.get("ASSIGNED_BY_ID")) for item in items if item.get("ASSIGNED_BY_ID") is not None}
        users = await self._load_users(client, user_ids)

        categories_response = await self._deal_categories_handler(client, params={}, cursor=None)
        categories_map = _index_by_keys(categories_response.data, ("ID",))

        category_ids: Set[str] = {
            _safe_str(item.get("CATEGORY_ID")) or "0" for item in items if item.get("CATEGORY_ID") is not None
        }
        if any(item.get("CATEGORY_ID") is None for item in items):
            category_ids.add("0")

        stages_by_category: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for category_id in category_ids:
            if category_id is None:
                continue
            payload_id: Any
            try:
                payload_id = int(category_id)
            except (ValueError, TypeError):
                payload_id = category_id
            stages_response = await self._deal_stages_handler(
                client,
                params={"id": payload_id},
                cursor=None,
            )
            stages_by_category[category_id] = _index_by_keys(stages_response.data, ("STATUS_ID", "ID"))

        for item in enriched:
            meta = _ensure_meta(item)

            assigned_key = _safe_str(item.get("ASSIGNED_BY_ID"))
            if assigned_key and assigned_key in users:
                meta["responsible"] = _build_user_summary(assigned_key, users[assigned_key])

            category_key = _safe_str(item.get("CATEGORY_ID")) or "0"
            category_data = categories_map.get(category_key)
            if category_data:
                meta["category"] = _build_enum_summary(category_key, category_data)

            stage_key = _safe_str(item.get("STAGE_ID"))
            stage_map = stages_by_category.get(category_key) or {}
            stage_data = stage_map.get(stage_key) if stage_key else None
            if not stage_data and stage_key and ":" in stage_key:
                # Some stage identifiers include category prefix C{ID}:STAGE
                stage_data = stage_map.get(stage_key.split(":", 1)[1])
            if stage_key and stage_data:
                meta["stage"] = _build_enum_summary(stage_key, stage_data)

        return enriched

    async def _enrich_tasks(self, client: BitrixClient, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not items:
            return items

        enriched: List[Dict[str, Any]] = [copy.deepcopy(item) for item in items]

        user_ids: Set[str] = set()
        for item in items:
            for key in ("RESPONSIBLE_ID", "CREATED_BY", "CREATED_BY_ID"):
                user_value = item.get(key)
                key_value = _safe_str(user_value)
                if key_value:
                    user_ids.add(key_value)

        users = await self._load_users(client, user_ids)

        status_response = await self._task_statuses_handler(client, params={}, cursor=None)
        status_map = _index_by_keys(status_response.data, ("ID", "VALUE"))

        priority_response = await self._task_priorities_handler(client, params={}, cursor=None)
        priority_map = _index_by_keys(priority_response.data, ("ID", "VALUE"))

        for item in enriched:
            meta = _ensure_meta(item)

            responsible_key = _safe_str(item.get("RESPONSIBLE_ID"))
            if responsible_key and responsible_key in users:
                meta["responsible"] = _build_user_summary(responsible_key, users[responsible_key])

            creator_key = _safe_str(item.get("CREATED_BY") or item.get("CREATED_BY_ID"))
            if creator_key and creator_key in users:
                meta["creator"] = _build_user_summary(creator_key, users[creator_key])

            status_key = _safe_str(item.get("STATUS"))
            status_data = status_map.get(status_key) if status_key else None
            if status_key and status_data:
                meta["status"] = _build_enum_summary(status_key, status_data)

            priority_key = _safe_str(item.get("PRIORITY"))
            priority_data = priority_map.get(priority_key) if priority_key else None
            if priority_key and priority_data:
                meta["priority"] = _build_enum_summary(priority_key, priority_data)

        return enriched

    def _apply_semantic_groups(self, items: List[Dict[str, Any]]) -> None:
        for entry in items:
            semantics = _extract_semantics(entry)
            if semantics:
                entry["group"] = semantics
                entry["groupName"] = _semantic_group_label(semantics)

    async def _status_dictionary_handler(
        self,
        client: BitrixClient,
        params: Dict[str, Any],
        cursor: Optional[str],
        *,
        resource: str,
        entity_id: str,
    ) -> ResourceQueryResponse:
        payload = copy.deepcopy(params) if params else {}
        filters = copy.deepcopy(payload.get("filter", {}))
        filters.setdefault("ENTITY_ID", entity_id)
        payload["filter"] = filters

        async def fetch() -> ResourceQueryResponse:
            response = await _list_entities(
                client,
                resource=resource,
                method="crm.status.list",
                params=payload,
                cursor=None,
            )
            self._apply_semantic_groups(response.data)
            return response

        return await self._cacheable_query(
            resource=resource,
            params=payload,
            cursor=cursor,
            fetcher=fetch,
        )

    async def _lead_statuses_handler(
        self, client: BitrixClient, params: Dict[str, Any], cursor: Optional[str]
    ) -> ResourceQueryResponse:
        return await self._status_dictionary_handler(
            client,
            params,
            cursor,
            resource="crm/lead_statuses",
            entity_id="STATUS",
        )

    async def _lead_sources_handler(
        self, client: BitrixClient, params: Dict[str, Any], cursor: Optional[str]
    ) -> ResourceQueryResponse:
        return await self._status_dictionary_handler(
            client,
            params,
            cursor,
            resource="crm/lead_sources",
            entity_id="SOURCE",
        )

    async def _currencies_handler(
        self, client: BitrixClient, params: Dict[str, Any], cursor: Optional[str]
    ) -> ResourceQueryResponse:
        payload = copy.deepcopy(params) if params else {}

        async def fetch() -> ResourceQueryResponse:
            return await _list_entities(
                client,
                resource="crm/currencies",
                method="crm.currency.list",
                params=payload,
                cursor=None,
            )

        return await self._cacheable_query(
            resource="crm/currencies",
            params=payload,
            cursor=cursor,
            fetcher=fetch,
        )

    async def _deal_categories_handler(
        self, client: BitrixClient, params: Dict[str, Any], cursor: Optional[str]
    ) -> ResourceQueryResponse:
        payload = copy.deepcopy(params) if params else {}

        async def fetch() -> ResourceQueryResponse:
            return await _list_entities(
                client,
                resource="crm/deal_categories",
                method="crm.dealcategory.list",
                params=payload,
                cursor=None,
            )

        return await self._cacheable_query(
            resource="crm/deal_categories",
            params=payload,
            cursor=cursor,
            fetcher=fetch,
        )

    async def _deal_stages_handler(
        self, client: BitrixClient, params: Dict[str, Any], cursor: Optional[str]
    ) -> ResourceQueryResponse:
        payload = copy.deepcopy(params) if params else {}
        if "id" not in payload and "categoryId" in payload:
            payload["id"] = payload.pop("categoryId")
        payload.setdefault("id", 0)

        async def fetch() -> ResourceQueryResponse:
            response = await _list_entities(
                client,
                resource="crm/deal_stages",
                method="crm.dealcategory.stage.list",
                params=payload,
                cursor=None,
            )
            self._apply_semantic_groups(response.data)
            return response

        return await self._cacheable_query(
            resource="crm/deal_stages",
            params=payload,
            cursor=cursor,
            fetcher=fetch,
        )

    async def _leads_handler(self, client: BitrixClient, params: Dict[str, Any], cursor: Optional[str]) -> ResourceQueryResponse:
        response = await _list_entities(
            client,
            resource="crm/leads",
            method="crm.lead.list",
            params=params,
            cursor=cursor,
        )
        response.data = await self._enrich_leads(client, response.data)
        return response

    async def _contacts_handler(self, client: BitrixClient, params: Dict[str, Any], cursor: Optional[str]) -> ResourceQueryResponse:
        return await _list_entities(
            client,
            resource="crm/contacts",
            method="crm.contact.list",
            params=params,
            cursor=cursor,
        )

    async def _task_field_handler(
        self,
        client: BitrixClient,
        params: Dict[str, Any],
        cursor: Optional[str],
        *,
        resource: str,
        field_key: str,
    ) -> ResourceQueryResponse:
        payload = copy.deepcopy(params) if params else {}

        async def fetch() -> ResourceQueryResponse:
            try:
                response = await client.call_method("tasks.task.getFields", payload)
            except BitrixAPIError as exc:
                raise UpstreamError(message=str(exc), payload=exc.payload, status_code=502) from exc

            fields = response.get("result") or {}
            if isinstance(fields, dict) and "fields" in fields and isinstance(fields["fields"], dict):
                fields = fields["fields"]
            field_definition = None
            if isinstance(fields, dict):
                field_definition = fields.get(field_key) or fields.get(field_key.lower())
            items = _normalize_enum_items(field_definition)
            metadata = _metadata(resource, client.settings)
            return ResourceQueryResponse(metadata=metadata, data=items, next_cursor=None)

        return await self._cacheable_query(
            resource=resource,
            params=payload,
            cursor=cursor,
            fetcher=fetch,
        )

    async def _task_statuses_handler(
        self, client: BitrixClient, params: Dict[str, Any], cursor: Optional[str]
    ) -> ResourceQueryResponse:
        return await self._task_field_handler(
            client,
            params,
            cursor,
            resource="tasks/statuses",
            field_key="STATUS",
        )

    async def _task_priorities_handler(
        self, client: BitrixClient, params: Dict[str, Any], cursor: Optional[str]
    ) -> ResourceQueryResponse:
        return await self._task_field_handler(
            client,
            params,
            cursor,
            resource="tasks/priorities",
            field_key="PRIORITY",
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
        response = await _list_entities(
            client,
            resource="crm/tasks",
            method="tasks.task.list",
            params=params,
            cursor=cursor,
        )
        response.data = await self._enrich_tasks(client, response.data)
        return response

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
