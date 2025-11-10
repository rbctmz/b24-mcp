# Bitrix24 MCP Server

FastAPI-based Model Context Protocol (MCP) server that exposes Bitrix24 CRM data and actions to LLM agents. The server translates MCP resource and tool calls into Bitrix24 REST API requests.

## Features

- MCP resources for listing deals, leads, contacts, users, and tasks
- MCP tools for retrieving CRM entities (deals, leads, contacts, users, tasks)
- Локализованные подсказки для MCP (русский язык), включая structuredContent и предупреждения о пропущенных аргументах
- Ответы инструментов соответствуют CallToolResult (поля `content`, `structuredContent`, `isError`) совместимому с fastmcp
- Configurable via environment variables (`.env`)
- HTTPX-based Bitrix24 client with retry/backoff
- Async FastAPI application ready for Docker or local execution
- Pytest suite with in-memory Bitrix24 client stubs

## Подсказки MCP и шпаргалки

- Все тексты подсказок, описания инструментов и готовые payload'ы хранятся в `mcp_server/app/docs/prompts_ru.md`. При изменении файла сервер автоматически подхватывает новые инструкции без правок в коде.
- Ответ `initialize` содержит `structuredInstructions` и `instructionNotes` с примерами: как получить свежие лиды (`order = {"DATE_MODIFY": "DESC"}`) и как задавать диапазоны дат через `>=DATE_CREATE`, `<=DATE_CREATE`.
- MCP-инструменты возвращают `structuredContent` с полным ответом Bitrix24 и предупреждениями. Если вызов `getLeads` не содержит диапазона по дате, сервер добавляет сообщение и логирует предупреждение.
- Доступен ресурс `bitrix24_leads_guide`, который отдаёт шпаргалку с типовыми сценариями (свежие лиды, выборка за сегодня, фильтр по статусу) и правилами комбинирования фильтров.
- Структура `prompts_ru.md` предусматривает локализацию: для новой локали достаточно добавить файл `prompts_<locale>.md` и обновить настройки.

## Формат ответа инструментов (CallToolResult)

- MCP инструменты (`/mcp/tool/call`, JSON-RPC `tools/call`, WebSocket/SSE) возвращают словарь формата:

```json
{
  "content": [
    {"type": "text", "text": "crm/leads: получено 42 записей. Полный ответ в structuredContent.result."},
    {"type": "text", "text": "Внимание: Добавьте фильтры диапазона ..."} // опционально
  ],
  "structuredContent": {
    "metadata": {"provider": "bitrix24", "tool": "getLeads", "resource": "crm/leads"},
    "request": {"order": {"DATE_MODIFY": "DESC"}, "filter": {...}},
    "result": {...},            // исходный ответ Bitrix24
    "warnings": [...]           // опционально
  },
  "isError": false
}
```

- Поле `structuredContent` хранит исходный REST payload, поэтому клиенты могут продолжать использовать `metadata` и `result`.
- Предупреждения о пропущенных датах и других критичных аргументах добавляются в `structuredContent.warnings` и дублируются в `content`.
- SSE/WebSocket трансляции используют тот же CallToolResult, что исключает ошибки валидатора fastmcp.

## Project Layout

```
mcp_server/
  app/
    main.py            # FastAPI application factory and lifespan management
    settings.py        # Pydantic settings loaded from environment
    bitrix_client.py   # Async HTTP client wrapper for Bitrix24 REST API
    exceptions.py      # Shared exception types for MCP responses
    dependencies.py    # FastAPI dependencies for resource/tool registries
    mcp/
      schemas.py       # Pydantic models for MCP requests/responses
      resources.py     # Resource registry (crm/deals, crm/leads, ...)
      tools.py         # Tool registry (getDeals, getLeads, ...)
      routes.py        # MCP endpoints (`/mcp/index`, `/mcp/resource/query`, `/mcp/tool/call`)
tests/
  test_resources.py    # Resource query tests
  test_tools.py        # Tool call tests
  conftest.py          # Shared fixtures and settings overrides
```

## Getting Started

### 1. Configure environment

Create `.env` based on `.env.example`:

```bash
cp .env.example .env
```

Update the following values:

- `BITRIX_BASE_URL`: your Bitrix24 REST endpoint (usually `<portal>/rest`)
- `BITRIX_TOKEN`: webhook key or OAuth access token
- `BITRIX_INSTANCE_NAME` (optional): identifier used in MCP metadata
- `SERVER_*`: customize local server host/port/log level if required

### 2. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

### 3. Run the server (local)

```bash
uvicorn mcp_server.app.main:app --reload
```

Health check:

```bash
curl http://localhost:8000/healthz
```

MCP discovery:

```bash
curl http://localhost:8000/mcp/index
```

### 4. Run tests

```bash
pytest
```

### 5. Run with Docker (optional)

```bash
docker build -t b24-mcp .
docker run --rm -p 8000:8000 --env-file .env b24-mcp
```

> **Note:** The provided `.env` file is mounted as environment variables inside the container. Ensure it contains valid Bitrix24 credentials before starting the container.

## Bitrix Token Requirements

- The server authenticates requests to Bitrix24 via the `BITRIX_TOKEN` environment variable.
- You can supply either:
  - **Inbound webhook key** (recommended for service integrations) — create in Bitrix24 and ensure it has access to CRM entities (deals, leads, contacts) and tasks.
  - **OAuth access token** — ensure the application scopes cover at least `crm`, `task`, and user directory access.
- Token must remain secret. Store it only in `.env`, CI secrets, or secure secret stores; never commit to source control.
- When rotating tokens, simply update the value in `.env` or provided secret source and restart the MCP server.

## MCP Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/mcp/index` | GET | Lists available resources and tools |
| `/mcp/resource/query` | POST | Queries a resource (`crm/deals`, `crm/leads`, `crm/contacts`, `crm/users`, `crm/tasks`) |
| `/mcp/tool/call` | POST | Executes a tool (`getDeals`, `getLeads`, `getContacts`, `getUsers`, `getTasks`) |

### Example resource query

```bash
curl -X POST http://localhost:8000/mcp/resource/query \
  -H "Content-Type: application/json" \
  -d '{"resource": "crm/deals", "params": {"select": ["ID", "TITLE"], "filter": {">OPPORTUNITY": 10000}}}'
```

### Example tool call

```bash
curl -X POST http://localhost:8000/mcp/tool/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "getDeals", "params": {"select": ["ID", "TITLE"], "filter": {">OPPORTUNITY": 10000}}}'
```

## Deployment Notes

- Use Docker or a process manager (systemd, supervisord) to host the FastAPI app.
- Ensure `.env` is stored securely and not committed to source control.
- For production, configure HTTPS termination and add authentication in front of the MCP server if required.

## Local WebSocket / CORS testing

- During local development the MCP server accepts WebSocket connections at `ws://<host>:<port>/mcp`.
- By default the application is configured to accept origins from `http://localhost` and `http://127.0.0.1`.
- If you see `403 Forbidden` when attempting to open a WebSocket, try supplying an explicit `Origin` header with your client
  (for example `Origin: http://localhost`) or update the `allow_origins` setting in `mcp_server/app/main.py`.

Testing examples:

```bash
# quick HTTP index check
curl -sS http://127.0.0.1:8000/mcp/index | jq .

# JSON-RPC handshake over HTTP GET
curl -sS http://127.0.0.1:8000/mcp | jq .

# websocat with explicit Origin header (recommended when debugging CORS)
websocat -H 'Origin: http://localhost' ws://127.0.0.1:8000/mcp

# FastMCP CLI (if installed) to test MCP handshake
python -m fastmcp.cli connect ws://127.0.0.1:8000/mcp
```

Note: For production deployments, restrict `allow_origins` to trusted domains and enable TLS (`wss://`).

### Server-Sent Events (SSE) streaming

This MCP server exposes a simple Server-Sent Events endpoint at `/mcp/sse`.
Use SSE when you want a streaming transport from server → client. The server
will send an initial handshake payload on connect and will broadcast tool and
resource results to connected SSE clients.

How it works:
- Connect a client to `GET /mcp/sse` to receive events (Content-Type `text/event-stream`).
- Send JSON-RPC requests via `POST /mcp` (the server will reply to the POST and
  also broadcast results to SSE subscribers).
- For local testing use the following commands:

```bash
# Tail the HTTP index
curl -sS http://127.0.0.1:8000/mcp/index | jq .

# Connect to SSE (example using curl) — note: curl will not nicely render continuous SSE output
# but can be used to test the handshake
curl -v http://127.0.0.1:8000/mcp/sse

# Send initialize over HTTP JSON-RPC (you should also see this payload on the SSE connection)
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | jq .

# Health endpoint
curl -sS http://127.0.0.1:8000/mcp/health | jq .
```

For production, replace curl with a proper SSE client (browser EventSource or an SSE-capable client library) and secure the connection with TLS (`https`/`wss`).

## MCP Client Setup (Claude, Codex, Cursor)

The server can be used by any MCP-capable client. Below are quick-start
examples for the most common desktop clients. Adjust paths for your
operating system and restart the client after editing its config.

### Claude Desktop

1. Ensure the MCP server is running locally (`uvicorn mcp_server.app.main:app --reload`).
2. Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
   (macOS) or `%AppData%\Claude\claude_desktop_config.json` (Windows).
3. Add an entry under `mcpServers`:

```jsonc
{
  "mcpServers": {
    "bitrix24": {
      "command": "/Users/you/Documents/GitHub/b24-mcp/.venv/bin/uvicorn",
      "args": [
        "mcp_server.app.main:app",
        "--host", "127.0.0.1",
        "--port", "8000",
        "--reload"
      ],
      "env": {
        "BITRIX_BASE_URL": "https://your-portal.bitrix24.ru/rest",
        "BITRIX_TOKEN": "xxxxx"
      }
    }
  }
}
```

Restart Claude Desktop and the Bitrix24 MCP server will appear in the MCP
servers menu.

### Codex CLI

1. Run the MCP server (`uvicorn mcp_server.app.main:app --reload`).
2. Update `~/.codex/config.toml` and add an entry beneath `[mcp_servers]`:

```toml
[mcp_servers.bitrix24]
url = "http://127.0.0.1:8000/mcp"
```

3. Restart the Codex CLI; run `codex mcp list` to verify the connection.

### Cursor IDE

1. Start the MCP server locally.
2. Edit `~/.cursor/mcp.json` (Cursor creates the file automatically after the
   first launch) and add a new server definition:

```jsonc
{
  "mcpServers": {
    "bitrix24": {
      "url": "http://127.0.0.1:8000/mcp",
      "timeout": 30000,
      "name": "Bitrix24 MCP"
    }
  }
}
```

After saving the file, reopen Cursor. The Bitrix24 MCP server will be available
in the MCP panel and can be enabled per project.

## License

MIT License. See [LICENSE](LICENSE) for details.
