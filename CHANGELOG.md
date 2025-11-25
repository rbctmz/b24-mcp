# Changelog

## Unreleased

- Приведён формат ответов `/mcp/tool/call`, JSON-RPC `tools/call`, SSE и WebSocket к CallToolResult (`content`, `structuredContent`, `isError`) для совместимости с fastmcp.
- Сохранён исходный payload Bitrix24 в `structuredContent`, добавлены текстовые резюме и предупреждения.
- Дополнены автотесты (`tests/test_tools.py`) проверками CallToolResult, SSE и WebSocket трансляций.

## 0.2.0

- Добавлен MCP-ресурс `versions/releases` с удобной историей релизов и описанием GitHub-линков; документация, prompts и тесты обновлены.
- Реализована синхронизация с GitHub Releases (`GITHUB_RELEASES_REPO`, `GITHUB_TOKEN`, тайм-аут и кеш), с автоматическим откатом на локальный `CHANGELOG.md`, если GitHub недоступен.

## 0.1.0

- Реализованы основные MCP-ресурсы (deals, leads, contacts, users, tasks, словари, шпаргалка по лидам) с обогащением `_meta` и кэшированием справочников.
- Добавлены инструменты `getDeals`, `getLeads`, `getContacts`, `getUsers`, `getTasks`, `getCompanies`, `getCompany`, `addCommentToDeal`, `updateDeal`, `createTask`, `callBitrixMethod` и `getLeadCalls`, включая поддержку структурированной информации и пагинации.
- Настроены локализованные подсказки, рекомендации по фильтрам, warnings, timezone-aware даты, HTTPX-клиент с ретраями, Pytest-стабы, Docker-совместимый FastAPI и Claude Desktop stdio-прокси.
