from __future__ import annotations

from fastapi.testclient import TestClient


def test_tool_get_deals(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.deal.list"] = {
        "result": [{"ID": "1"}],
        "total": 1,
    }

    response = client.post(
        "/mcp/tool/call",
        json={"tool": "getDeals", "params": {"select": ["ID"]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["tool"] == "getDeals"
    assert body["metadata"]["resource"] == "crm/deals"
    assert body["result"]["result"][0]["ID"] == "1"


def test_tool_get_tasks(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["tasks.task.list"] = {
        "result": [{"id": 7}],
        "total": 1,
    }

    response = client.post(
        "/mcp/tool/call",
        json={"tool": "getTasks", "params": {"select": ["ID"]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["tool"] == "getTasks"
    assert body["metadata"]["resource"] == "crm/tasks"
    assert body["result"]["result"][0]["id"] == 7


def test_tool_call_jsonrpc(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.lead.list"] = {
        "result": [{"ID": "55", "TITLE": "Lead via JSONRPC"}],
        "total": 1,
    }

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {
                "name": "getLeads",
                "arguments": {"select": ["ID", "TITLE"]},
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 99
    result = payload["result"]
    assert result["metadata"]["tool"] == "getLeads"
    assert result["result"]["result"][0]["TITLE"] == "Lead via JSONRPC"
