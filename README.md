# Bitrix24 MCP Server

FastAPI-based Model Context Protocol (MCP) server that exposes Bitrix24 CRM data and actions to LLM agents. The server translates MCP resource and tool calls into Bitrix24 REST API requests.

## Features

- MCP resources for listing deals, leads, contacts, users, and tasks
- MCP tools for retrieving CRM entities (deals, leads, contacts, users, tasks)
- Configurable via environment variables (`.env`)
- HTTPX-based Bitrix24 client with retry/backoff
- Async FastAPI application ready for Docker or local execution
- Pytest suite with in-memory Bitrix24 client stubs

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

## License

MIT License. See [LICENSE](LICENSE) for details.
