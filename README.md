# Bitrix24 MCP Server

FastAPI-based Model Context Protocol (MCP) server that exposes Bitrix24 CRM data and actions to LLM agents. The server translates MCP resource and tool calls into Bitrix24 REST API requests.

## Features

- MCP resources for listing deals, leads, contacts, users, tasks, currencies, and Bitrix24 dictionaries (lead stages/sources, deal categories/stages, task statuses/priorities)
- MCP tools for retrieving CRM entities (deals, leads, contacts, users, tasks) and companies (list/detail via `getCompanies`/`getCompany`)
- Localized MCP prompts (Russian), including structuredContent and warnings for missing arguments
- Tool responses conform to CallToolResult (fields `content`, `structuredContent`, `isError`) compatible with fastmcp
- Uniform warnings and recommended date filters for all tools, allowing clients to automatically retry requests with adjustments
- Resource responses include `_meta` blocks with human-readable labels (responsible user, stage, source, priority, etc.)
- Tool responses for `getLeads` now reuse the cached `crm/leads` dictionary so they ship the same `_meta` data (responsible, creator, modifier, status, source, currency), expose `structuredContent.aggregates` with counts, include `structuredContent.hints.copyableFilter` (примеры недельного фильтра/iter) so агент может копировать фильтр для следующего запроса, а предупреждения по `toolWarnings.getLeads` больше не приводят только к диапазону «сегодня» — теперь пример показывает последнюю неделю с `>=DATE_CREATE`/`<=DATE_CREATE`.
- Date-range hints, warnings, and weekly samples respect a configurable timezone (`SERVER_TIMEZONE`, default `UTC`), so the generated `YYYY-MM-DDTHH:MM:SS±HH:MM` boundaries match your portal’s local day.
- Configurable via environment variables (`.env`)
- HTTPX-based Bitrix24 client with retry/backoff
- Async FastAPI application ready for Docker or local execution
- Pytest suite with in-memory Bitrix24 client stubs
- Claude Desktop stdio proxy (`mcp_stdio_proxy.py`) with configurable base URL/timeout via environment

## MCP Prompts and Cheat Sheets

- All prompt texts, tool descriptions, and ready-made payloads are stored in `mcp_server/app/docs/prompts_ru.md`. When the file is changed, the server automatically picks up new instructions without code modifications.
- The `initialize` response contains `structuredInstructions` and `instructionNotes` with examples: how to get fresh leads (`order = {"DATE_MODIFY": "DESC"}`) and how to set date ranges via `>=DATE_CREATE`, `<=DATE_CREATE`.
- MCP tools return `structuredContent` with the full Bitrix24 response and warnings. If no date range is provided, any list tool (`getDeals`, `getLeads`, `getContacts`, `getUsers`, `getTasks`, `getCompanies`) adds a message, recommended filters, and `suggestedFix`, allowing fastmcp/SGR to automatically retry the request.
- The `bitrix24_leads_guide` resource provides a cheat sheet with typical scenarios (fresh leads, today's selection, status filter) and rules for combining filters.
- The `prompts_ru.md` structure provides for localization: for a new locale, it is enough to add a `prompts_<locale>.md` file and update the settings.

## Tool Response Format (CallToolResult)

- MCP tools (`/mcp/tool/call`, JSON-RPC `tools/call`, WebSocket/SSE) return a dictionary in the format:

```json
{
  "content": [
    {"type": "text", "text": "crm/leads: 42 records received. Full response in structuredContent.result."},
    {"type": "text", "text": "Warning: Add range filters ..."} // optional
  ],
  "structuredContent": {
    "metadata": {"provider": "bitrix24", "tool": "getLeads", "resource": "crm/leads"},
    "request": {"order": {"DATE_MODIFY": "DESC"}, "filter": {...}},
    "result": {...},            // original Bitrix24 response
    "warnings": [...]           // optional
  },
  "isError": false
}
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
mmp@m copypaste? Wait patch wants to change line 105 from ` ``` ` to ` ```text `. Need patch near that line. We'll produce patch.

- The `structuredContent` field stores the original REST payload, so clients can continue to use `metadata` and `result`.
- Warnings about missing dates and other critical arguments are added to `structuredContent.warnings`, and specific filters and sorts to apply are available in `structuredContent.suggestedFix.filters`.
- SSE/WebSocket transmissions use the same CallToolResult, which eliminates fastmcp validator errors.
- For list tools the server additionally exposes `structuredContent.pagination` (`limit`, `start`, `next`, `total`, `fetched`), so you can immediately report the total count or use `next` to page through the full selection.
- For dictionaries like `crm/lead_statuses` and `crm/deal_stages` we now include each stage’s `group`/`groupName` derived from its semantics (`process` → «В работе», `success` → «Заключена», `failure` → «Провалена»), so agents can filter or aggregate by status groups directly.
- `getLeads` now supports `statusSemantics` (or alias `groupSemantics`) — a list of semantic groups (`process`, `success`, `failure`). The server resolves them into the corresponding `STATUS_ID` values before handing the filter to Bitrix, so you can request “лиды в работе” without managing the ID list yourself.
- Added `callBitrixMethod` so you can proxy arbitrary REST calls (for example, `crm.activity.list` to fetch calls by `OWNER_TYPE_ID`/`TYPE_ID`). This keeps MCP flexible while reusing the same logging/warnings/pagination wrappers.
- Added `getLeadCalls`, which combines `crm.activity.list` + `crm.activity.get` + `voximplant.statistic.get` to produce a detailed call log for a lead (`date`, `CALL_ID`, `duration`, and recording info).

## Resource Response Metadata (`_meta`)

- Every entity returned via `crm/deals`, `crm/leads`, and `crm/tasks` is enriched with a `_meta` section that contains human-readable descriptors resolved through cached Bitrix24 dictionaries:

```json
{
  "ID": "123",
  "ASSIGNED_BY_ID": "42",
  "STATUS_ID": "NEW",
  "_meta": {
    "responsible": {
      "id": "42",
      "name": "Анна Иванова",
      "email": "anna@example.com"
    },
    "status": {
      "id": "NEW",
      "name": "Новый"
    },
    "source": {
      "id": "CALL",
      "name": "Звонок"
    }
  }
}
```

- Available enrichments today:
  - Deals: `responsible`, `category`, `stage`
  - Leads: `responsible`, `creator`, `modifier`, `status`, `source`, `currency`
  - Tasks: `responsible`, `creator`, `status`, `priority`
- Each `_meta.<key>` entry exposes an `id`, a `name`, and `raw` (original Bitrix24 dictionary entry) so MCP clients can keep working with the underlying IDs when needed.
- Cached dictionaries (`crm/currencies`, `crm/lead_statuses`, `crm/lead_sources`, `crm/deal_categories`, `crm/deal_stages`, `tasks/statuses`, `tasks/priorities`) are also exposed as standalone MCP resources for direct lookups.

## Project Layout

```text
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
- `SERVER_TIMEZONE` (optional): IANA timezone (default `UTC`) used when building date-range warnings/hints so agents always see consistent local boundaries.

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

### 6. Connect Claude Desktop via stdio proxy

Use the included `mcp_stdio_proxy.py` script to bridge Claude Desktop (stdio-based MCP client) with the HTTP server:

1. Ensure the MCP server is running locally (defaults to `http://127.0.0.1:8000`).
2. Optional environment variables for the proxy:
   - `MCP_PROXY_BASE_URL` – override the target server URL (defaults to `http://127.0.0.1:8000`).
   - `MCP_PROXY_TIMEOUT` – request timeout in seconds (defaults to `30`).
3. Update Claude Desktop settings (`~/Library/Application Support/Claude/Settings/settings.json`):

   ```json
   {
     "mcpServers": {
       "b24-mcp": {
         "command": "/Users/gregkisel/Documents/GitHub/b24-mcp/.venv/bin/python",
         "args": [
           "/Users/gregkisel/Documents/GitHub/b24-mcp/mcp_stdio_proxy.py"
         ],
         "cwd": "/Users/gregkisel/Documents/GitHub/b24-mcp",
         "env": {
           "MCP_PROXY_BASE_URL": "http://127.0.0.1:8000",
           "MCP_PROXY_TIMEOUT": "30"
         },
         "autoStart": false
       }
     }
   }
   ```

   Adjust the paths if your checkout lives elsewhere or you use a different Python interpreter.

4. Restart Claude Desktop and select the `b24-mcp` MCP server. The proxy skips JSON-RPC notifications (no `id`) to avoid spurious errors while forwarding responses untouched.

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
| `/mcp/tool/call` | POST | Executes a tool (`getDeals`, `getLeads`, `getContacts`, `getUsers`, `getTasks`, `getCompanies`, `getCompany`) |

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
- Send JSON-RPC requests via `POST /mcp` (the server will reply to the POST and also broadcast results to SSE subscribers).
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
    "b24-mcp": {
      "command": "/Users/gregkisel/Documents/GitHub/b24-mcp/.venv/bin/python",
      "args": [
        "/Users/gregkisel/Documents/GitHub/b24-mcp/mcp_stdio_proxy.py"
      ],
      "cwd": "/Users/gregkisel/Documents/GitHub/b24-mcp",
      "env": {
        "MCP_PROXY_BASE_URL": "http://127.0.0.1:8000",
        "MCP_PROXY_TIMEOUT": "30"
      },
      "autoStart": false
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
