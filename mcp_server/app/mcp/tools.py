from __future__ import annotations

import copy
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from ..bitrix_client import BitrixAPIError, BitrixClient
from ..exceptions import ToolNotFoundError, UpstreamError
from ..prompt_loader import get_tool_docs, get_tool_warning_rules
from ..settings import BitrixSettings
from .date_ranges import DateRangeBuilder, DateRangeError
from .resources import _safe_str, ResourceRegistry
from .schemas import MCPMetadata, ResourceQueryRequest, ToolCallRequest, ToolCallResponse, ToolDescriptor

ToolHandler = Callable[[BitrixClient, Dict[str, Any]], Awaitable[ToolCallResponse]]

logger = logging.getLogger(__name__)

_DEFAULT_LOCALE = "ru"


_TOOL_CONFIG: Dict[str, Dict[str, str]] = {
    "getDeals": {"entity": "сделки", "method": "crm.deal.list", "resource": "crm/deals"},
    "getLeads": {"entity": "лиды", "method": "crm.lead.list", "resource": "crm/leads"},
    "callBitrixMethod": {"entity": "вызов REST-метода", "method": "call", "resource": "bitrix/method"},
    "getLeadCalls": {"entity": "звонки лида", "method": "crm.activity.list", "resource": "bitrix/lead_calls"},
    "getContacts": {"entity": "контакты", "method": "crm.contact.list", "resource": "crm/contacts"},
    "getUsers": {"entity": "пользователи", "method": "user.get", "resource": "crm/users"},
    "getTasks": {"entity": "задачи", "method": "tasks.task.list", "resource": "crm/tasks"},
    "getCompanies": {"entity": "компании", "method": "crm.company.list", "resource": "crm/companies"},
    "getCompany": {"entity": "компания", "method": "crm.company.get", "resource": "crm/company"},
}


def _metadata(tool: str, settings: BitrixSettings, resource: Optional[str] = None) -> MCPMetadata:
    return MCPMetadata(provider="bitrix24", tool=tool, resource=resource, instance_name=settings.instance_name)


def _normalize_semantics(semantics: Union[str, List[str], None]) -> Optional[str]:
    if semantics is None:
        return None
    if isinstance(semantics, (list, tuple, set)):
        for item in semantics:
            if item:
                semantics = item
                break
        else:
            return None
    return str(semantics).upper()


async def _call_bitrix(
    client: BitrixClient,
    *,
    tool: str,
    method: str,
    payload: Dict[str, Any],
    resource: Optional[str] = None,
    warnings: Optional[List[Dict[str, Any]]] = None,
    aggregates: Optional[Dict[str, Any]] = None,
    hints: Optional[Dict[str, Any]] = None,
) -> ToolCallResponse:
    try:
        response = await client.call_method(method, payload)
    except BitrixAPIError as exc:
        raise UpstreamError(message=str(exc), payload=exc.payload, status_code=502) from exc

    return _build_tool_response(
        tool=tool,
        resource=resource,
        settings=client.settings,
        payload=payload,
        response=response,
        warnings=warnings,
        aggregates=aggregates,
        hints=hints,
    )


def _build_tool_response(
    *,
    tool: str,
    resource: Optional[str],
    settings: BitrixSettings,
    payload: Dict[str, Any],
    response: Dict[str, Any],
    warnings: Optional[List[Dict[str, Any]]] = None,
    aggregates: Optional[Dict[str, Any]] = None,
    hints: Optional[Dict[str, Any]] = None,
) -> ToolCallResponse:
    metadata = _metadata(tool, settings, resource=resource)
    structured_payload: Dict[str, Any] = {
        "metadata": metadata.model_dump(exclude_none=True),
        "request": payload,
        "result": response,
    }
    if aggregates:
        structured_payload["aggregates"] = aggregates
    if hints:
        structured_payload["hints"] = hints
    pagination = _extract_pagination(response)
    if pagination:
        structured_payload["pagination"] = pagination
    content_messages = []
    if warnings:
        structured_payload["warnings"] = warnings
        suggested_filters = []
        for warning in warnings:
            message = warning.get("message") if isinstance(warning, dict) else str(warning)
            appendix = ""
            if isinstance(warning, dict) and warning.get("suggested_filters"):
                appendix = f" Рекомендуемые фильтры: {warning['suggested_filters']}"
                suggested_filters.append(warning["suggested_filters"])
            content_messages.append({"type": "text", "text": f"⚠️ {message}{appendix}"})
        if suggested_filters:
            structured_payload["suggestedFix"] = {"filters": suggested_filters}

    resource_name = metadata.resource or metadata.tool or "Bitrix24"
    items_count = _count_result_items(response)
    total_items = _extract_total(response)
    if items_count is not None:
        if total_items is not None:
            summary_text = f"{resource_name}: получено {items_count} из {total_items} записей. Полный ответ в structuredContent.result."
        else:
            summary_text = f"{resource_name}: получено {items_count} записей. Полный ответ в structuredContent.result."
    else:
        summary_text = f"{resource_name}: ответ получен. Полный результат в structuredContent.result."
    content_messages.append({"type": "text", "text": summary_text})

    return ToolCallResponse(
        metadata=metadata,
        result=response,
        structuredContent=structured_payload,
        content=content_messages,
        warnings=warnings,
        is_error=bool(warnings),
    )


def _extract_pagination(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    total = _extract_total(payload)
    next_cursor = payload.get("next")
    limit = payload.get("limit")
    fetched = None
    if isinstance(payload.get("result"), list):
        fetched = len(payload["result"])
    pagination: Dict[str, Any] = {}
    if limit is not None:
        pagination["limit"] = limit
    if payload.get("start") is not None:
        pagination["start"] = payload["start"]
    if next_cursor is not None:
        pagination["next"] = str(next_cursor)
    if total is not None:
        pagination["total"] = total
    if fetched is not None:
        pagination["fetched"] = fetched
    return pagination or None


def _count_result_items(payload: Dict[str, Any]) -> Optional[int]:
    if isinstance(payload.get("result"), list):
        return len(payload["result"])
    return None


def _extract_total(payload: Dict[str, Any]) -> Optional[int]:
    if "total" in payload and isinstance(payload["total"], int):
        return payload["total"]
    if "total" in payload and isinstance(payload["total"], str):
        try:
            return int(payload["total"])
        except ValueError:
            return None
    return None


class ToolRegistry:
    def __init__(self, client: BitrixClient, resource_registry: ResourceRegistry, date_range_builder: DateRangeBuilder):
        self._client = client
        self._resource_registry = resource_registry
        self._range_builder = date_range_builder
        self._locale = _DEFAULT_LOCALE
        self._tool_docs = get_tool_docs(self._locale)
        self._warning_rules = get_tool_warning_rules(self._locale)
        self._registry: Dict[str, ToolHandler] = {
            "getDeals": self._get_deals,
            "getLeads": self._get_leads,
            "callBitrixMethod": self._call_bitrix_method,
            "getLeadCalls": self._get_lead_calls,
            "getContacts": self._get_contacts,
            "getUsers": self._get_users,
            "getTasks": self._get_tasks,
            "getCompanies": self._get_companies,
            "getCompany": self._get_company,
        }
        self._descriptors: Dict[str, ToolDescriptor] = {}
        for tool_name, config in _TOOL_CONFIG.items():
            doc = self._tool_docs.get(tool_name, {})
            description = doc.get("description", _tool_description(entity=config["entity"], method=config["method"]))
            input_schema = doc.get("inputSchema")
            if input_schema is None:
                input_schema = _list_args_schema()
            else:
                input_schema = copy.deepcopy(input_schema)
            if tool_name == "callBitrixMethod":
                input_schema = _call_bitrix_method_schema()
            if tool_name == "getLeadCalls":
                input_schema = _lead_calls_schema()
            if tool_name == "getCompany":
                input_schema = _company_get_schema()
            self._descriptors[tool_name] = ToolDescriptor(
                name=tool_name,
                description=description,
                inputSchema=input_schema,
            )

    def descriptors(self) -> List[ToolDescriptor]:
        return list(self._descriptors.values())

    async def call(self, request: ToolCallRequest) -> ToolCallResponse:
        handler = self._registry.get(request.tool)
        if handler is None:
            raise ToolNotFoundError(request.tool)
        return await handler(self._client, request.params)

    def _collect_warnings(self, tool_name: str, params: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        rules = self._warning_rules.get(tool_name, []) or []
        messages: List[Dict[str, Any]] = []
        for rule in rules:
            message = rule.get("message")
            if not message:
                continue
            check_type = rule.get("check")
            if check_type == "require_date_range" and self._requires_date_range_warning(rule, params):
                warning_data: Dict[str, Any] = {"message": self._format_warning_message(message)}
                suggestion = self._build_date_range_suggestion(rule)
                if suggestion:
                    warning_data["suggested_filters"] = suggestion
                messages.append(warning_data)
        if messages:
            logger.info("[%s] Issued warnings: %s", tool_name, messages)
            return messages
        return None

    @staticmethod
    def _requires_date_range_warning(rule: Dict[str, Any], params: Dict[str, Any]) -> bool:
        filter_map = params.get("filter")
        if not isinstance(filter_map, dict) or not filter_map:
            return True
        fields = rule.get("fields") or []
        if not fields:
            return False
        return not any(ToolRegistry._has_date_range(filter_map, field) for field in fields)

    @staticmethod
    def _has_date_range(filter_map: Dict[str, Any], field: str) -> bool:
        lower_prefixes = (">=", ">")
        upper_prefixes = ("<=", "<")
        lower = upper = False
        for key in filter_map.keys():
            if not isinstance(key, str):
                continue
            if key.endswith(field):
                if key.startswith(lower_prefixes):
                    lower = True
                if key.startswith(upper_prefixes):
                    upper = True
            if lower and upper:
                return True
        return False

    def _format_warning_message(self, template: str) -> str:
        placeholders = self._range_builder.placeholders("today", "iso")
        placeholders.update(self._range_builder.week_placeholders())
        return template.format(**placeholders)

    def _build_date_range_suggestion(self, rule: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        suggestion_type = rule.get("suggestion", "today")
        format_hint = rule.get("suggestion_format", "iso")
        semantic = rule.get("suggestion_semantics")
        try:
            window = self._range_builder.build_range(suggestion_type)
        except DateRangeError:
            return None
        start_value = self._range_builder.format_value(window.start, format_hint)
        end_value = self._range_builder.format_value(window.end, format_hint)
        placeholders = self._range_builder.placeholders(suggestion_type, format_hint)
        placeholders.update(self._range_builder.week_placeholders())
        template_filters = rule.get("suggested_filters")
        if isinstance(template_filters, dict):
            formatted = {}
            for key, value in template_filters.items():
                if isinstance(value, str):
                    formatted[key] = value.format(**placeholders)
                else:
                    formatted[key] = value
            return formatted
        filters = {
            f">={rule.get('suggestion_field', 'DATE_CREATE')}": start_value,
            f"<={rule.get('suggestion_field', 'DATE_CREATE')}": end_value,
        }
        if semantic:
            filters["=STATUS_SEMANTIC_ID"] = semantic
        return filters

    async def _get_leads(self, client: BitrixClient, params: Dict[str, Any]) -> ToolCallResponse:
        warnings = self._collect_warnings("getLeads", params)
        config = _TOOL_CONFIG["getLeads"]
        payload = dict(params)
        semantics_filter = payload.pop("statusSemantics", None) or payload.pop("groupSemantics", None)
        if semantics_filter:
            semantic_value = _normalize_semantics(semantics_filter)
            if semantic_value:
                filter_map = payload.setdefault("filter", {})
                filter_map["=STATUS_SEMANTIC_ID"] = semantic_value
                logger.info("[getLeads] Applied semantics filter %s", semantic_value)
        requested_limit = None
        if "limit" in payload and payload["limit"] is not None:
            try:
                requested_limit = int(payload["limit"])
            except (TypeError, ValueError):
                requested_limit = None
        if requested_limit is not None:
            payload["limit"] = min(requested_limit, 500)
        raw_order = payload.get("order")
        if not raw_order:
            payload["order"] = {"DATE_MODIFY": "DESC"}
        resource_request = ResourceQueryRequest(resource=config["resource"], params=payload)
        resource_response = await self._resource_registry.query(resource_request)
        aggregates = self._build_lead_aggregates(resource_response.data)
        hints = self._build_weekly_hint(payload)
        result_payload: Dict[str, Any] = {
            "result": resource_response.data,
            "limit": payload.get("limit"),
            "start": payload.get("start"),
            "order": payload.get("order"),
        }
        if resource_response.total is not None:
            result_payload["total"] = resource_response.total
        if resource_response.next_cursor is not None:
            result_payload["next"] = resource_response.next_cursor
        pagination_info = {
            "limit": payload.get("limit"),
            "start": payload.get("start"),
            "next": resource_response.next_cursor,
            "total": resource_response.total,
            "fetched": len(resource_response.data),
        }
        response = _build_tool_response(
            tool="getLeads",
            resource=config["resource"],
            settings=client.settings,
            payload=payload,
            response=result_payload,
            warnings=warnings,
            aggregates=aggregates,
            hints=hints,
        )
        if response.structuredContent is not None:
            response.structuredContent.setdefault("pagination", pagination_info)
        return response

    @staticmethod
    def _build_lead_aggregates(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        responsible: Dict[str, Dict[str, Any]] = {}
        status: Dict[str, Dict[str, Any]] = {}
        for item in items:
            assigned_key = _safe_str(item.get("ASSIGNED_BY_ID"))
            if assigned_key:
                entry = responsible.setdefault(assigned_key, {"count": 0})
                entry["count"] += 1
                name = item.get("_meta", {}).get("responsible", {}).get("name")
                if name:
                    entry["name"] = name
            status_key = _safe_str(item.get("STATUS_ID"))
            if status_key:
                entry = status.setdefault(status_key, {"count": 0})
                entry["count"] += 1
                name = item.get("_meta", {}).get("status", {}).get("name")
                if name:
                    entry["name"] = name
        aggregates: Dict[str, Any] = {}
        if responsible:
            aggregates["responsible"] = responsible
        if status:
            aggregates["status"] = status
        return aggregates

    def _build_weekly_hint(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        window = self._range_builder.build_range("last_week")
        limit_value = 50
        limit = payload.get("limit")
        if isinstance(limit, int):
            limit_value = limit
        elif isinstance(limit, str):
            try:
                limit_value = int(limit)
            except ValueError:
                limit_value = 50
        return {
            "message": "Пример недельного фильтра для следующего запроса.",
            "copyableFilter": {
                "filter": {
                    ">=DATE_CREATE": window.iso_start(),
                    "<=DATE_CREATE": window.iso_end(),
                },
                "order": {"DATE_MODIFY": "DESC"},
                "limit": limit_value,
            },
        }

    async def _call_bitrix_method(self, client: BitrixClient, params: Dict[str, Any]) -> ToolCallResponse:
        warnings = self._collect_warnings("callBitrixMethod", params)
        config = _TOOL_CONFIG["callBitrixMethod"]
        method = params.get("method")
        if not isinstance(method, str):
            raise ValueError("method is required")
        method_params = params.get("params", {})
        if not isinstance(method_params, dict):
            raise ValueError("params must be an object")
        response = await client.call_method(method, method_params)
        return _build_tool_response(
            tool="callBitrixMethod",
            resource=config["resource"],
            settings=client.settings,
            payload=params,
            response=response,
            warnings=warnings,
        )

    async def _get_lead_calls(self, client: BitrixClient, params: Dict[str, Any]) -> ToolCallResponse:
        warnings = self._collect_warnings("getLeadCalls", params)
        owner_id = params.get("ownerId") or params.get("leadId")
        if not owner_id:
            raise ValueError("ownerId (lead ID) is required")
        filter_map = dict(params.get("filter") or {})
        filter_map.update({"OWNER_TYPE_ID": 1, "OWNER_ID": owner_id, "TYPE_ID": 2})
        list_params = {
            "filter": filter_map,
            "select": params.get("select") or ["ID", "CALL_ID", "START_TIME", "DURATION", "PHONE_FROM", "RESULT"],
            "order": params.get("order") or {"START_TIME": "DESC"},
            "limit": params.get("limit") or 10,
        }
        response = await client.call_method("crm.activity.list", list_params)
        activities = response.get("result") or []
        enriched: List[Dict[str, Any]] = []
        for activity in activities:
            act_id = activity.get("ID")
            detail = None
            recording = None
            if act_id:
                detail_resp = await client.call_method("crm.activity.get", {"ID": act_id})
                detail = detail_resp.get("result")
                call_id = detail.get("CALL_ID") if isinstance(detail, dict) else None
                if call_id:
                    record_resp = await client.call_method("voximplant.statistic.get", {"CALL_ID": call_id})
                    recording = record_resp.get("result")
            enriched.append(
                {
                    "timeline": activity,
                    "activity": detail,
                    "recording": recording,
                }
            )
        payload = {"filter": filter_map, "order": list_params["order"], "limit": list_params["limit"]}
        result_payload = {"result": enriched, "total": response.get("total")}
        pagination = _extract_pagination(response)
        response_tool = _build_tool_response(
            tool="getLeadCalls",
            resource=_TOOL_CONFIG["getLeadCalls"]["resource"],
            settings=client.settings,
            payload=payload,
            response=result_payload,
            warnings=warnings,
        )
        if pagination and response_tool.structuredContent is not None:
            response_tool.structuredContent.setdefault("pagination", pagination)
        return response_tool

    async def _get_deals(self, client: BitrixClient, params: Dict[str, Any]) -> ToolCallResponse:
        warnings = self._collect_warnings("getDeals", params)
        config = _TOOL_CONFIG["getDeals"]
        payload = dict(params)
        semantics_filter = payload.pop("stageSemantics", None)
        if semantics_filter:
            semantic_value = _normalize_semantics(semantics_filter)
            if semantic_value:
                filter_map = payload.setdefault("filter", {})
                filter_map["=STATUS_SEMANTIC_ID"] = semantic_value
                logger.info("[getDeals] Applied stage semantics filter %s", semantic_value)
        return await _call_bitrix(
            client,
            tool="getDeals",
            resource=config["resource"],
            method=config["method"],
            payload=payload,
            warnings=warnings,
        )

    async def _get_contacts(self, client: BitrixClient, params: Dict[str, Any]) -> ToolCallResponse:
        warnings = self._collect_warnings("getContacts", params)
        config = _TOOL_CONFIG["getContacts"]
        return await _call_bitrix(
            client,
            tool="getContacts",
            resource=config["resource"],
            method=config["method"],
            payload=params,
            warnings=warnings,
        )

    async def _get_users(self, client: BitrixClient, params: Dict[str, Any]) -> ToolCallResponse:
        warnings = self._collect_warnings("getUsers", params)
        config = _TOOL_CONFIG["getUsers"]
        return await _call_bitrix(
            client,
            tool="getUsers",
            resource=config["resource"],
            method=config["method"],
            payload=params,
            warnings=warnings,
        )

    async def _get_companies(self, client: BitrixClient, params: Dict[str, Any]) -> ToolCallResponse:
        warnings = self._collect_warnings("getCompanies", params)
        config = _TOOL_CONFIG["getCompanies"]
        return await _call_bitrix(
            client,
            tool="getCompanies",
            resource=config["resource"],
            method=config["method"],
            payload=params,
            warnings=warnings,
        )

    async def _get_company(self, client: BitrixClient, params: Dict[str, Any]) -> ToolCallResponse:
        warnings = self._collect_warnings("getCompany", params)
        config = _TOOL_CONFIG["getCompany"]
        company_id = params.get("id") or params.get("ID")
        if not company_id:
            raise ValueError("id is required")
        payload: Dict[str, Any] = {"ID": company_id}
        if "select" in params:
            payload["select"] = params["select"]
        response = await client.call_method(config["method"], payload)
        return _build_tool_response(
            tool="getCompany",
            resource=config["resource"],
            settings=client.settings,
            payload=payload,
            response=response,
            warnings=warnings,
        )

    async def _get_tasks(self, client: BitrixClient, params: Dict[str, Any]) -> ToolCallResponse:
        warnings = self._collect_warnings("getTasks", params)
        config = _TOOL_CONFIG["getTasks"]
        return await _call_bitrix(
            client,
            tool="getTasks",
            resource=config["resource"],
            method=config["method"],
            payload=params,
            warnings=warnings,
        )


def _list_args_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "description": (
            "Параметры методов списка Bitrix24. Используйте их, чтобы выбрать поля, "
            "настроить фильтры и пагинацию."
        ),
        "additionalProperties": False,
        "properties": {
            "select": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Коды полей, которые нужно вернуть вместо набора по умолчанию.",
            },
            "filter": {
                "type": "object",
                "additionalProperties": True,
                "description": "Фильтры Bitrix формата `<оператор><поле>` → значение.",
            },
            "order": {
                "type": "object",
                "additionalProperties": True,
                "description": "Сортировка: код поля → направление (`ASC` или `DESC`).",
            },
            "start": {"type": "integer", "minimum": 0, "description": "Смещение пагинации."},
            "limit": {"type": "integer", "minimum": 1, "description": "Максимум записей."},
        },
        "examples": [
            {
                "select": ["ID", "TITLE", "DATE_CREATE"],
                "filter": {"=CATEGORY_ID": "0", ">=DATE_CREATE": "2024-01-01"},
                "order": {"DATE_CREATE": "DESC"},
                "limit": 20,
            }
        ],
    }


def _call_bitrix_method_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "method": {"type": "string", "description": "Имя REST метода Bitrix"},
            "params": {
                "type": "object",
                "additionalProperties": True,
                "description": "Параметры, передаваемые непосредственно в Bitrix REST.",
            },
        },
        "required": ["method"],
        "examples": [
            {
                "method": "crm.activity.list",
                "params": {
                    "filter": {
                        "OWNER_TYPE_ID": 1,
                        "OWNER_ID": 19721,
                        "TYPE_ID": 2,
                    },
                    "select": ["ID", "SUBJECT", "START_TIME"],
                    "order": {"START_TIME": "DESC"},
                    "limit": 5,
                },
            }
        ],
    }


def _lead_calls_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "ownerId": {"type": ["string", "integer"], "description": "ID лида"},
            "limit": {"type": "integer", "minimum": 1, "default": 10},
            "filter": {"type": "object", "additionalProperties": True},
            "select": {"type": "array", "items": {"type": "string"}},
            "order": {"type": "object", "additionalProperties": True},
        },
        "required": ["ownerId"],
    }


def _company_get_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": ["string", "integer"], "description": "ID компании"},
            "select": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Список кодов полей, которые нужно вернуть",
            },
        },
        "required": ["id"],
    }


def _tool_description(*, entity: str, method: str) -> str:
    return (
        f"Получает {entity} через Bitrix24 `{method}`. Поддерживает `select`, `filter`, `order`, "
        "`start` и `limit`."
    )
