from __future__ import annotations

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
    assert payload["serverInfo"]["name"] == "Bitrix24 MCP Server"
    assert payload["protocolVersion"] == {"major": 1, "minor": 0}
    assert "resources" in payload["capabilities"]
    assert "tools" in payload["capabilities"]
    assert any(resource["uri"] == "crm/deals" for resource in payload["resources"])


def test_mcp_initialize_alias(app, client: TestClient) -> None:
    response = client.post("/mcp/initialize", json={"client": "test"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["protocolVersion"] == {"major": 1, "minor": 0}
    assert any(resource["uri"] == "crm/deals" for resource in payload["resources"])


def test_mcp_get_healthcheck(client: TestClient) -> None:
    response = client.get("/mcp")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "MCP endpoint is alive"}


def test_mcp_options_healthcheck(client: TestClient) -> None:
    response = client.options("/mcp")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "MCP endpoint is alive"}


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
