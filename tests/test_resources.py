from __future__ import annotations

import json

from fastapi.testclient import TestClient


def test_resource_query_deals(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.deal.list"] = {
        "result": [{"ID": "1", "TITLE": "Test deal"}],
        "total": 1,
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/deals", "params": {"select": ["ID", "TITLE"]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["resource"] == "crm/deals"
    assert body["metadata"]["provider"] == "bitrix24"
    assert body["data"][0]["ID"] == "1"
    assert body["next_cursor"] is None


def test_resource_query_with_pagination(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.contact.list"] = {
        "result": [{"ID": "10"}],
        "total": 2,
        "next": 50,
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/contacts", "params": {"limit": 1}, "cursor": "0"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["resource"] == "crm/contacts"
    assert payload["next_cursor"] == "50"


def test_resource_unknown(client: TestClient) -> None:
    response = client.post(
        "/mcp/resource/query",
        json={"resource": "unknown", "params": {}},
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["detail"]["type"] == "resource_not_found"


def test_mcp_handshake(app, client: TestClient) -> None:
    response = client.post("/mcp", json={"client": "test"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "initialize"
    params = payload["params"]
    assert params["serverInfo"]["name"] == "Bitrix24 MCP Server"
    assert params["protocolVersion"] == {"major": 1, "minor": 0}
    assert "resources" in params["capabilities"]
    assert "tools" in params["capabilities"]
    assert any(resource["uri"] == "crm/deals" for resource in params["resources"])


def test_mcp_initialize_alias(app, client: TestClient) -> None:
    response = client.post("/mcp/initialize", json={"client": "test"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "initialize"
    params = payload["params"]
    assert params["protocolVersion"] == {"major": 1, "minor": 0}
    assert any(resource["uri"] == "crm/deals" for resource in params["resources"])


def test_mcp_get_entrypoint(app, client: TestClient) -> None:
    response = client.get("/mcp")

    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "initialize"
    params = payload["params"]
    assert params["protocolVersion"] == {"major": 1, "minor": 0}
    assert any(resource["uri"] == "crm/deals" for resource in params["resources"])


def test_mcp_healthcheck(client: TestClient) -> None:
    response = client.get("/mcp/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "MCP endpoint is alive"}


def test_mcp_tools_list(client: TestClient) -> None:
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 1
    tools = payload["result"]["tools"]
    assert isinstance(tools, list)
    assert any(tool["name"] == "getLeads" for tool in tools)


def test_mcp_resources_list(client: TestClient) -> None:
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 42, "method": "resources/list", "params": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 42
    resources = payload["result"]["resources"]
    assert isinstance(resources, list)
    assert any(resource["uri"] == "crm/deals" for resource in resources)


def test_mcp_resources_query_jsonrpc(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.deal.list"] = {
        "result": [{"ID": "1", "TITLE": "JSONRPC Deal"}],
        "total": 1,
    }

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 7,
            "method": "resources/query",
            "params": {
                "uri": "crm/deals",
                "arguments": {"select": ["ID", "TITLE"]},
                "cursor": None,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 7
    result = payload["result"]
    assert result["metadata"]["resource"] == "crm/deals"
    assert result["data"][0]["TITLE"] == "JSONRPC Deal"


def test_mcp_options_healthcheck(client: TestClient) -> None:
    response = client.options("/mcp")

    assert response.status_code == 204
    assert response.content == b""
    assert response.headers["Access-Control-Allow-Methods"] == "GET, POST, OPTIONS"


def test_well_known_oauth_root(client: TestClient) -> None:
    response = client.get("/.well-known/oauth-authorization-server")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "message": "OAuth discovery metadata is not configured for this MCP server.",
    }


def test_well_known_oauth_suffix(client: TestClient) -> None:
    response = client.get("/.well-known/oauth-authorization-server/mcp")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "message": "OAuth discovery metadata is not configured for this MCP server.",
    }


def test_mcp_scoped_well_known(client: TestClient) -> None:
    response = client.get("/mcp/.well-known/oauth-authorization-server")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "message": "OAuth discovery metadata is not configured for this MCP server.",
    }
