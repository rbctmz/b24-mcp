# Changelog

## Unreleased

- Приведён формат ответов `/mcp/tool/call`, JSON-RPC `tools/call`, SSE и WebSocket к CallToolResult (`content`, `structuredContent`, `isError`) для совместимости с fastmcp.
- Сохранён исходный payload Bitrix24 в `structuredContent`, добавлены текстовые резюме и предупреждения.
- Дополнены автотесты (`tests/test_tools.py`) проверками CallToolResult, SSE и WebSocket трансляций.
