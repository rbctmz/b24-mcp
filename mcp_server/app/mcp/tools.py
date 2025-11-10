from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional
import logging
import copy
from datetime import datetime, timezone

from ..bitrix_client import BitrixAPIError, BitrixClient
from ..exceptions import ToolNotFoundError, UpstreamError
from ..settings import BitrixSettings
from .schemas import MCPMetadata, ToolCallRequest, ToolCallResponse, ToolDescriptor
from ..prompt_loader import get_tool_docs, get_tool_warning_rules

ToolHandler = Callable[[BitrixClient, Dict[str, Any]], Awaitable[ToolCallResponse]]

logger = logging.getLogger(__name__)

_DEFAULT_LOCALE = "ru"


_TOOL_CONFIG: Dict[str, Dict[str, str]] = {
    "getDeals": {"entity": "сделки", "method": "crm.deal.list", "resource": "crm/deals"},
    "getLeads": {"entity": "лиды", "method": "crm.lead.list", "resource": "crm/leads"},
    "getContacts": {"entity": "контакты", "method": "crm.contact.list", "resource": "crm/contacts"},
    "getUsers": {"entity": "пользователи", "method": "user.get", "resource": "crm/users"},
    "getTasks": {"entity": "задачи", "method": "tasks.task.list", "resource": "crm/tasks"},
}


def _metadata(tool: str, settings: BitrixSettings, resource: Optional[str] = None) -> MCPMetadata:
    return MCPMetadata(provider="bitrix24", tool=tool, resource=resource, instance_name=settings.instance_name)


async def _call_bitrix(
    client: BitrixClient,
    *,
    tool: str,
    method: str,
    payload: Dict[str, Any],
    resource: Optional[str] = None,
    warnings: Optional[List[str]] = None,
) -> ToolCallResponse:
    metadata = _metadata(tool, client.settings, resource=resource)
    is_error = bool(warnings)
    try:
        response = await client.call_method(method, payload)
    except BitrixAPIError as exc:  # pragma: no cover - simple passthrough
        raise UpstreamError(message=str(exc), payload=exc.payload, status_code=502) from exc

    structured_payload: Dict[str, Any] = {
        "metadata": metadata.model_dump(exclude_none=True),
        "request": payload,
        "result": response,
    }
    content_messages: List[Dict[str, str]] = []

    if warnings:
        structured_payload["warnings"] = warnings
        for warning_text in warnings:
            content_messages.append({"type": "text", "text": f"⚠️ {warning_text}"})

    items_count: Optional[int] = None
    if isinstance(response, dict):
        payload_items = response.get("result")
        if isinstance(payload_items, list):
            items_count = len(payload_items)

    resource_name = metadata.resource or metadata.tool or "Bitrix24"
    if items_count is not None:
        summary_text = (
            f"{resource_name}: получено {items_count} записей. Полный ответ в structuredContent.result."
        )
    else:
        summary_text = f"{resource_name}: ответ получен. Полный результат в structuredContent.result."
    content_messages.append({"type": "text", "text": summary_text})

    response_kwargs: Dict[str, Any] = {
        "metadata": metadata,
        "result": response,
        "structuredContent": structured_payload,
        "content": content_messages,
        "is_error": is_error,
    }
    if warnings:
        response_kwargs["warnings"] = warnings

    return ToolCallResponse(**response_kwargs)


class ToolRegistry:
    """Registers and resolves MCP tools."""

    def __init__(self, client: BitrixClient) -> None:
        self._client = client
        self._locale = _DEFAULT_LOCALE
        self._tool_docs = get_tool_docs(self._locale)
        self._warning_rules = get_tool_warning_rules(self._locale)

        self._registry: Dict[str, ToolHandler] = {
            "getDeals": self._get_deals,
            "getLeads": self._get_leads,
            "getContacts": self._get_contacts,
            "getUsers": self._get_users,
            "getTasks": self._get_tasks,
        }

        self._descriptors: Dict[str, ToolDescriptor] = {}
        for tool_name, config in _TOOL_CONFIG.items():
            doc = self._tool_docs.get(tool_name, {})
            description = doc.get(
                "description",
                _tool_description(entity=config["entity"], method=config["method"]),
            )
            input_schema = doc.get("inputSchema")
            if input_schema is None:
                input_schema = _list_args_schema()
            else:
                input_schema = copy.deepcopy(input_schema)
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

    def _collect_warnings(self, tool_name: str, params: Dict[str, Any]) -> Optional[List[str]]:
        messages = self._evaluate_warnings(tool_name, params)
        if messages:
            logger.info("[%s] Issued warnings: %s", tool_name, messages)
            return messages
        return None

    def _evaluate_warnings(self, tool_name: str, params: Dict[str, Any]) -> List[str]:
        rules = self._warning_rules.get(tool_name, []) or []
        messages: List[str] = []
        for rule in rules:
            check_type = rule.get("check")
            message = rule.get("message")
            if not message:
                continue
            if check_type == "require_date_range":
                if self._requires_date_range_warning(rule, params):
                    messages.append(self._format_warning_message(message))
            else:
                logger.debug("[%s] Unknown warning check type: %s", tool_name, check_type)
        return messages

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
        lower = False
        upper = False
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

    @staticmethod
    def _format_warning_message(template: str) -> str:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(hour=23, minute=59, second=59)
        return template.format(
            today_start=start.isoformat(),
            today_end=end.isoformat(),
        )

    async def _get_deals(self, client: BitrixClient, params: Dict[str, Any]) -> ToolCallResponse:
        warnings = self._collect_warnings("getDeals", params)
        config = _TOOL_CONFIG["getDeals"]
        return await _call_bitrix(
            client,
            tool="getDeals",
            resource=config["resource"],
            method=config["method"],
            payload=params,
            warnings=warnings,
        )

    async def _get_leads(self, client: BitrixClient, params: Dict[str, Any]) -> ToolCallResponse:
        warnings = self._collect_warnings("getLeads", params)
        config = _TOOL_CONFIG["getLeads"]
        payload = dict(params)
        logger.info(f"[getLeads] Input params: {params}")

        # Разбор и валидация параметра limit до использования
        requested_limit: Optional[int] = None
        if "limit" in params:
            raw_limit = params.get("limit")
            if raw_limit is None:
                logger.info("[getLeads] limit provided but is None; ignoring")
            else:
                try:
                    requested_limit = int(raw_limit)
                except (ValueError, TypeError) as e:
                    logger.warning(f"[getLeads] Invalid limit value: {raw_limit}, error: {e}")
                    requested_limit = None

        if requested_limit is not None:
            # enforce server-side cap
            cap = 500
            payload["limit"] = requested_limit if requested_limit <= cap else cap
            logger.info(f"[getLeads] Setting limit in payload: {payload['limit']}")
        else:
            logger.info("[getLeads] No valid limit specified in params; not setting limit")

        raw_order = payload.get("order")
        if not raw_order:
            payload["order"] = {"DATE_MODIFY": "DESC"}
            logger.info("[getLeads] Applying default order by DATE_MODIFY DESC for freshness")
        else:
            logger.info(f"[getLeads] Using custom order: {raw_order}")

        logger.info(f"[getLeads] Final payload to Bitrix24: {payload}")

        response = await _call_bitrix(
            client,
            tool="getLeads",
            resource=config["resource"],
            method=config["method"],
            payload=payload,
            warnings=warnings,
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
            "Параметры методов списка Bitrix24. Используйте их, чтобы выбрать поля, настроить фильтры и пагинацию."
        ),
        "additionalProperties": False,
        "properties": {
            "select": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Коды полей, которые нужно вернуть вместо набора по умолчанию.",
                "examples": [["ID", "TITLE", "DATE_CREATE"]],
            },
            "filter": {
                "type": "object",
                "additionalProperties": True,
                "description": (
                    "Фильтры Bitrix формата `<оператор><поле>` → значение. Операторы: `=` `>` `<` `>=` `<=` `@` (IN). "
                    "Пример: `{\"=STATUS_ID\": \"NEW\", \">DATE_CREATE\": \"2024-01-01\"}`."
                ),
                "examples": [
                    {"=STATUS_ID": "NEW"},
                    {">DATE_CREATE": "2024-01-01"},
                    {"@ASSIGNED_BY_ID": ["123", "456"]},
                ],
            },
            "order": {
                "type": "object",
                "additionalProperties": True,
                "description": "Сортировка: код поля → направление (`ASC` или `DESC`).",
                "examples": [
                    {"DATE_CREATE": "DESC"},
                    {"ID": "ASC", "TITLE": "DESC"},
                ],
            },
            "start": {
                "type": "integer",
                "minimum": 0,
                "description": "Смещение пагинации. Передавайте `next` из предыдущего ответа.",
                "examples": [0, 50],
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "description": (
                    "Максимальное число записей в ответе. Bitrix24 обычно ограничивает его 50."
                ),
                "examples": [5, 20, 50],
            },
        },
        "required": [],
        "examples": [
            {
                "select": ["ID", "TITLE", "DATE_CREATE"],
                "filter": {"=CATEGORY_ID": "0", ">DATE_CREATE": "2024-01-01"},
                "order": {"DATE_CREATE": "DESC"},
                "limit": 20,
            }
        ],
    }


def _tool_description(*, entity: str, method: str) -> str:
    """Provide a consistent description explaining filter/sort usage to MCP clients."""

    return (
        f"Получает {entity} через Bitrix24 `{method}`. Поддерживает `select` (поля), "
        "`filter` (операторы `=`, `>=`, `<=`, `@` и т.д.), `order` (карта `ASC`/`DESC`), "
        "`start` (смещение) и `limit` (максимум записей, в пределах ограничений Bitrix24)."
    )
