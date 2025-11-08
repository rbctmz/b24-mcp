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

-   crm/deals
-   crm/leads
-   crm/contacts
-   crm/users
-   crm/tasks

## 5. MCP Tools

-   getDeals
-   getLeads
-   getContacts
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
