# Техническое Задание

## MCP-сервер для интеграции с Битрикс24

### Python / FastAPI / MCP Protocol

## 1. Цель проекта

Создать MCP-сервер на Python, обеспечивающий ИИ-агенту
стандартизированный доступ к данным Битрикс24.

## 2. Технологический стек

-   Python 3.10+
-   FastAPI
-   MCP Protocol
-   HTTPX
-   Pydantic v2

## 3. Архитектура

LLM → MCP Server → Bitrix24 REST API

## 4. MCP Resources

-   crm/deals — список сделок с _meta информацией (ответственный, стадия, направление)
-   crm/leads — список лидов с _meta (ответственный, стадия, источник)
-   crm/contacts — список контактов
-   crm/users — список пользователей портала
-   crm/tasks — список задач с _meta (ответственный, постановщик, статус, приоритет)
-   crm/lead_statuses — справочник стадий лидов (crm.status.list ENTITY_ID=STATUS)
-   crm/lead_sources — справочник источников лидов (ENTITY_ID=SOURCE)
-   crm/deal_categories — справочник направлений/воронок сделок
-   crm/deal_stages — стадии по воронкам (crm.dealcategory.stage.list)
-   tasks/statuses — справочник статусов задач (tasks.task.getFields → STATUS)
-   tasks/priorities — справочник приоритетов задач (tasks.task.getFields → PRIORITY)

## 5. MCP Tools

-   getDeals
-   getLeads
-   getContacts
-   getCompanies
-   getCompany
-   getUsers
-   getTasks
-   updateDeal
-   addCommentToDeal
-   createTask

## 6. Требования безопасности

-   Работает локально или в Docker
-   Ключи в .env

## 7. Структура проекта

mcp_server/app/...

## 8. Примеры MCP сообщений

tools.call, resource.query

## 9. Критерии приемки

-   Все Tools и Resources реализованы
-   README и тесты присутствуют

## 10. Обогащение данных (`_meta`)

-   Для ресурсов `crm/deals`, `crm/leads`, `crm/tasks` каждая запись дополняется блоком `_meta`, содержащим человекочитаемые поля:
    -   `responsible`, `creator` — сведения о пользователях (ФИО, email, должность)
    -   `status`, `stage`, `category`, `source`, `priority` — расшифровка кодов CRM/Tasks
    -   Каждое значение включает `id`, `name`, а также `raw` с оригинальным ответом Битрикс24
-   MCP‑клиентам рекомендуется использовать `_meta` для отображения в интерфейсе, сохраняя оригинальные идентификаторы из основного объекта.
-   Справочники, используемые для обогащения, доступны как отдельные ресурсы (см. раздел «MCP Resources»), что позволяет клиентам обновлять кэш или использовать собственные механизмы сопоставления.
