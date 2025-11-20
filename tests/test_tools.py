from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from mcp_server.app.mcp import routes


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
    assert body["isError"] is True
    assert body["structuredContent"]["metadata"]["tool"] == "getDeals"
    assert body["structuredContent"]["metadata"]["resource"] == "crm/deals"
    warnings = body["structuredContent"]["warnings"]
    assert warnings[0]["message"].startswith("Добавьте фильтры диапазона")
    assert set(warnings[0]["suggested_filters"].keys()) == {">=DATE_CREATE", "<=DATE_CREATE"}
    assert set(body["structuredContent"]["suggestedFix"]["filters"][0].keys()) == {
        ">=DATE_CREATE",
        "<=DATE_CREATE",
    }
    assert any(item["text"].startswith("⚠️") for item in body["content"])
    assert body["structuredContent"]["result"]["result"][0]["ID"] == "1"
    assert body["content"][-1]["type"] == "text"


def test_tool_get_contacts(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.contact.list"] = {
        "result": [{"ID": "2"}],
        "total": 1,
    }

    response = client.post(
        "/mcp/tool/call",
        json={"tool": "getContacts", "params": {"select": ["ID"]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["isError"] is True
    assert body["structuredContent"]["metadata"]["tool"] == "getContacts"
    assert body["structuredContent"]["metadata"]["resource"] == "crm/contacts"
    warnings = body["structuredContent"]["warnings"]
    assert warnings[0]["message"].startswith("Добавьте фильтры диапазона")
    assert set(warnings[0]["suggested_filters"].keys()) == {">=DATE_CREATE", "<=DATE_CREATE"}
    assert warnings[0]["suggested_filters"] == body["structuredContent"]["suggestedFix"]["filters"][0]
    assert any(item["text"].startswith("⚠️") for item in body["content"])
    assert body["structuredContent"]["result"]["result"][0]["ID"] == "2"


def test_tool_get_companies(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.company.list"] = {
        "result": [{"ID": "9"}],
        "total": 1,
    }

    response = client.post(
        "/mcp/tool/call",
        json={"tool": "getCompanies", "params": {"select": ["ID"]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["isError"] is True
    assert body["structuredContent"]["metadata"]["tool"] == "getCompanies"
    assert body["structuredContent"]["metadata"]["resource"] == "crm/companies"
    warnings = body["structuredContent"]["warnings"]
    assert warnings[0]["message"].startswith("Добавьте фильтры диапазона")
    assert set(warnings[0]["suggested_filters"].keys()) == {">=DATE_CREATE", "<=DATE_CREATE"}
    assert warnings[0]["suggested_filters"] == body["structuredContent"]["suggestedFix"]["filters"][0]
    assert any(item["text"].startswith("⚠️") for item in body["content"])
    assert body["structuredContent"]["result"]["result"][0]["ID"] == "9"


def test_tool_get_company(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.company.get"] = {
        "result": {"ID": "9", "TITLE": "НКМ"},
    }

    response = client.post(
        "/mcp/tool/call",
        json={"tool": "getCompany", "params": {"id": "9", "select": ["ID", "TITLE"]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["isError"] is False
    assert body["structuredContent"]["metadata"]["tool"] == "getCompany"
    assert body["structuredContent"]["metadata"]["resource"] == "crm/company"
    assert body["structuredContent"]["result"]["result"]["ID"] == "9"
    assert body["structuredContent"]["result"]["result"]["TITLE"] == "НКМ"


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
    assert body["isError"] is True
    assert body["structuredContent"]["metadata"]["tool"] == "getTasks"
    assert body["structuredContent"]["metadata"]["resource"] == "crm/tasks"
    warnings = body["structuredContent"]["warnings"]
    assert warnings[0]["message"].startswith("Добавьте фильтры диапазона")
    assert set(warnings[0]["suggested_filters"].keys()) == {">=CHANGED_DATE", "<=CHANGED_DATE"}
    for value in warnings[0]["suggested_filters"].values():
        assert "T" in value
        assert value.endswith((":00", ":59"))
    assert set(body["structuredContent"]["suggestedFix"]["filters"][0].keys()) == {
        ">=CHANGED_DATE",
        "<=CHANGED_DATE",
    }
    for value in body["structuredContent"]["suggestedFix"]["filters"][0].values():
        assert "T" in value
        assert value.endswith((":00", ":59"))
    assert any(item["text"].startswith("⚠️") for item in body["content"])
    assert body["structuredContent"]["result"]["result"][0]["id"] == 7
    assert body["content"][-1]["text"].startswith("crm/tasks")


def test_tool_get_users(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["user.get"] = {
        "result": [{"ID": "5"}],
        "total": 1,
    }

    response = client.post(
        "/mcp/tool/call",
        json={"tool": "getUsers", "params": {"select": ["ID"]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["isError"] is False
    assert body["structuredContent"]["metadata"]["tool"] == "getUsers"
    assert body["structuredContent"]["metadata"]["resource"] == "crm/users"
    assert "warnings" not in body["structuredContent"]
    assert len(body["content"]) == 1
    assert body["structuredContent"]["result"]["result"][0]["ID"] == "5"


def test_tasks_tool_no_warning_when_date_range_present(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["tasks.task.list"] = {
        "result": [{"id": 7}],
        "total": 1,
    }

    response = client.post(
        "/mcp/tool/call",
        json={
            "tool": "getTasks",
            "params": {
                "filter": {
                    ">=CHANGED_DATE": "2024-06-01",
                    "<=CHANGED_DATE": "2024-06-02",
                }
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["isError"] is False
    assert "warnings" not in body["structuredContent"]


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
    assert result["isError"] is True
    assert result["structuredContent"]["metadata"]["tool"] == "getLeads"
    warnings = result["structuredContent"]["warnings"]
    assert warnings[0]["message"].startswith("Добавьте фильтры диапазона")
    assert set(warnings[0]["suggested_filters"].keys()) == {">=DATE_CREATE", "<=DATE_CREATE"}
    assert set(result["structuredContent"]["suggestedFix"]["filters"][0].keys()) == {
        ">=DATE_CREATE",
        "<=DATE_CREATE",
    }
    assert any(item["text"].startswith("⚠️") for item in result["content"])
    assert result["structuredContent"]["result"]["result"] == []
    assert app.state.bitrix_client.calls == []


def test_tool_call_jsonrpc_with_date_filter(app, client: TestClient) -> None:
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
                "arguments": {
                    "select": ["ID", "TITLE"],
                    "filter": {
                        ">=DATE_CREATE": "2025-11-19T00:00:00Z",
                        "<=DATE_CREATE": "2025-11-19T23:59:59Z",
                    },
                },
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 99
    result = payload["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["metadata"]["tool"] == "getLeads"
    assert result["structuredContent"]["result"]["result"][0]["TITLE"] == "Lead via JSONRPC"


def test_leads_tool_warns_without_date_filter(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.lead.list"] = {
        "result": [{"ID": "55"}],
        "total": 1,
    }

    response = client.post(
        "/mcp/tool/call",
        json={"tool": "getLeads", "params": {"filter": {"=STATUS_ID": "NEW"}}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["isError"] is True
    assert body["structuredContent"]["metadata"]["tool"] == "getLeads"
    warnings = body["structuredContent"]["warnings"]
    assert warnings[0]["message"].startswith("Добавьте фильтры диапазона")
    assert set(warnings[0]["suggested_filters"].keys()) == {">=DATE_CREATE", "<=DATE_CREATE"}
    assert set(body["structuredContent"]["suggestedFix"]["filters"][0].keys()) == {
        ">=DATE_CREATE",
        "<=DATE_CREATE",
    }
    assert any(item["text"].startswith("⚠️") for item in body["content"])
    assert body["structuredContent"]["request"]["order"] == {"DATE_MODIFY": "DESC"}
    assert app.state.bitrix_client.calls == []


def test_leads_tool_no_warning_when_date_range_present(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.lead.list"] = {
        "result": [{"ID": "101"}],
        "total": 1,
    }

    response = client.post(
        "/mcp/tool/call",
        json={
            "tool": "getLeads",
            "params": {
                "filter": {
                    ">=DATE_CREATE": "2024-06-01",
                    "<=DATE_CREATE": "2024-06-02",
                }
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["isError"] is False
    assert body["structuredContent"]["metadata"]["tool"] == "getLeads"
    assert "warnings" not in body["structuredContent"]
    assert len(body["content"]) == 1


def test_leads_tool_sets_default_order_and_caps_limit(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.lead.list"] = {
        "result": [],
        "total": 0,
    }

    response = client.post(
        "/mcp/tool/call",
        json={
            "tool": "getLeads",
            "params": {
                "limit": 999,
                "filter": {
                    ">=DATE_CREATE": "2024-06-01",
                    "<=DATE_CREATE": "2024-06-02",
                },
            },
        },
    )

    assert response.status_code == 200
    calls = app.state.bitrix_client.calls
    assert len(calls) == 1
    method, payload = calls[0]
    assert method == "crm.lead.list"
    assert payload["limit"] == 500  # server-side cap
    assert payload["order"] == {"DATE_MODIFY": "DESC"}


def test_leads_tool_exposes_total_and_pagination(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.lead.list"] = {
        "result": [{"ID": "77"}],
        "total": 194,
        "next": 100,
    }

    response = client.post(
        "/mcp/tool/call",
        json={
            "tool": "getLeads",
            "params": {
                "filter": {
                    ">=DATE_CREATE": "2025-11-09T00:00:00Z",
                    "<=DATE_CREATE": "2025-11-16T23:59:59Z",
                },
                "limit": 100,
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    result_payload = body["structuredContent"]["result"]
    pagination = body["structuredContent"]["pagination"]

    assert result_payload["total"] == 194
    assert result_payload["next"] == "100"
    assert pagination["total"] == 194
    assert pagination["next"] == "100"
    assert pagination["limit"] == 100
    assert pagination["fetched"] == 1


def test_leads_tool_includes_weekly_hint(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.lead.list"] = {
        "result": [
            {"ID": "200", "ASSIGNED_BY_ID": "123", "STATUS_ID": "NEW"},
        ]
    }

    response = client.post(
        "/mcp/tool/call",
        json={
            "tool": "getLeads",
            "params": {
                "select": ["ID", "ASSIGNED_BY_ID", "STATUS_ID", "DATE_CREATE", "DATE_MODIFY"],
                "filter": {
                    ">=DATE_CREATE": "2024-06-01",
                    "<=DATE_CREATE": "2024-06-02",
                },
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    hints = body["structuredContent"].get("hints")
    assert hints is not None
    copyable = hints.get("copyableFilter")
    assert copyable is not None
    assert copyable["order"] == {"DATE_MODIFY": "DESC"}
    filter_map = copyable["filter"]
    assert ">=DATE_CREATE" in filter_map
    assert "<=DATE_CREATE" in filter_map
    assert copyable["limit"] == 50


def test_leads_tool_preserves_custom_order(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.lead.list"] = {
        "result": [],
        "total": 0,
    }

    response = client.post(
        "/mcp/tool/call",
        json={
            "tool": "getLeads",
            "params": {
                "order": {"DATE_CREATE": "ASC"},
                "limit": 5,
                "filter": {
                    ">=DATE_CREATE": "2024-06-01",
                    "<=DATE_CREATE": "2024-06-02",
                },
            },
        },
    )

    assert response.status_code == 200
    method, payload = app.state.bitrix_client.calls[-1]
    assert payload["order"] == {"DATE_CREATE": "ASC"}
    assert payload["limit"] == 5


def test_leads_tool_semantics_filter(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.status.list"] = {
        "result": [
            {"STATUS_ID": "NEW", "SEMANTICS": "process"},
            {"STATUS_ID": "FINAL_INVOICE", "SEMANTICS": "success"},
        ]
    }
    app.state.bitrix_client.responses["crm.lead.list"] = {
        "result": [{"ID": "99"}],
        "total": 1,
    }

    response = client.post(
        "/mcp/tool/call",
        json={
            "tool": "getLeads",
            "params": {
                "statusSemantics": ["process"],
                "filter": {
                    ">=DATE_CREATE": "2025-11-01T00:00:00Z",
                    "<=DATE_CREATE": "2025-11-01T23:59:59Z",
                },
            },
        },
    )

    assert response.status_code == 200
    lead_call = next((call for call in reversed(app.state.bitrix_client.calls) if call[0] == "crm.lead.list"), None)
    assert lead_call is not None
    _, payload = lead_call
    assert payload["filter"]["=STATUS_SEMANTIC_ID"] == "PROCESS"



def test_call_bitrix_method_forward_app_request(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.activity.list"] = {
        "result": [{"ID": "C1", "TYPE_ID": 2}],
        "total": 1,
    }

    response = client.post(
        "/mcp/tool/call",
        json={
            "tool": "callBitrixMethod",
            "params": {
                "method": "crm.activity.list",
                "params": {
                    "filter": {
                        "OWNER_TYPE_ID": 1,
                        "OWNER_ID": "19721",
                        "TYPE_ID": 2,
                    },
                    "select": ["ID", "TYPE_ID"],
                },
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["structuredContent"]["result"]["result"][0]["ID"] == "C1"


def test_get_lead_calls_sequence(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.activity.list"] = {
        "result": [{"ID": "A1"}, {"ID": "A2"}],
        "total": 2,
    }
    app.state.bitrix_client.responses["crm.activity.get"] = {
        "result": {"ID": "A1", "CALL_ID": "call-1", "DURATION": 60},
    }
    app.state.bitrix_client.responses["voximplant.statistic.get"] = {
        "result": {"CALL_ID": "call-1", "RECORDING_URL": "https://rec/1.mp3"}
    }

    response = client.post(
        "/mcp/tool/call",
        json={
            "tool": "getLeadCalls",
            "params": {
                "ownerId": 19721,
                "limit": 1,
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    records = body["structuredContent"]["result"]["result"]
    assert records[0]["activity"]["CALL_ID"] == "call-1"
    assert records[0]["recording"]["CALL_ID"] == "call-1"
    assert records[0]["recording"]["RECORDING_URL"] == "https://rec/1.mp3"

@pytest.mark.parametrize(
    ("tool", "method"),
    [
        ("getDeals", "crm.deal.list"),
        ("getContacts", "crm.contact.list"),
        ("getUsers", "user.get"),
        ("getTasks", "tasks.task.list"),
    ],
)
def test_other_tools_forward_payloads(app, client: TestClient, tool: str, method: str) -> None:
    app.state.bitrix_client.responses[method] = {"result": [{"ID": "1"}], "total": 1}

    response = client.post(
        "/mcp/tool/call",
        json={
            "tool": tool,
            "params": {
                "select": ["ID"],
                "filter": {
                    "=ID": "1",
                    ">=DATE_CREATE": "2024-06-01",
                    "<=DATE_CREATE": "2024-06-02",
                },
                "order": {"ID": "ASC"},
                "limit": 10,
            },
        },
    )

    assert response.status_code == 200
    called_method, payload = app.state.bitrix_client.calls[-1]
    assert called_method == method
    assert payload["select"] == ["ID"]
    assert payload["filter"] == {
        "=ID": "1",
        ">=DATE_CREATE": "2024-06-01",
        "<=DATE_CREATE": "2024-06-02",
    }
    assert payload["order"] == {"ID": "ASC"}
    assert payload["limit"] == 10


def test_tools_list_contains_localized_schema(app, client: TestClient) -> None:
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    tools = payload["result"]["tools"]
    leads_tool = next(tool for tool in tools if tool["name"] == "getLeads")
    assert "crm.lead.list" in leads_tool["description"]
    assert leads_tool["inputSchema"]["default"]["order"]["DATE_MODIFY"] == "DESC"
    assert leads_tool["inputSchema"]["properties"]["order"]["additionalProperties"]["enum"] == ["ASC", "DESC"]


def test_tool_call_broadcasts_call_tool_result_to_sse(app, client: TestClient) -> None:
    while routes.PENDING_SSE_EVENTS:
        routes.PENDING_SSE_EVENTS.popleft()

    app.state.bitrix_client.responses["crm.deal.list"] = {
        "result": [{"ID": "3"}],
        "total": 1,
    }

    response = client.post(
        "/mcp/tool/call",
        json={"tool": "getDeals", "params": {"select": ["ID"]}},
    )

    assert response.status_code == 200
    asyncio.get_event_loop().run_until_complete(asyncio.sleep(0))
    assert len(routes.PENDING_SSE_EVENTS) == 1
    message = routes.PENDING_SSE_EVENTS.popleft()
    assert message["jsonrpc"] == "2.0"
    assert message["method"] == "tools/call"
    call_result = message["params"]["result"]
    assert call_result["structuredContent"]["metadata"]["tool"] == "getDeals"
    assert call_result["content"][0]["type"] == "text"


def test_websocket_tools_call_returns_call_tool_result(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.lead.list"] = {
        "result": [{"ID": "77"}],
        "total": 1,
    }

    with client.websocket_connect("/mcp") as websocket:
        websocket.send_json(
            {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "getLeads",
                "arguments": {
                    "select": ["ID"],
                    "filter": {
                        ">=DATE_CREATE": "2024-06-01",
                        "<=DATE_CREATE": "2024-06-02",
                    },
                },
            },
        }
        )
        message = websocket.receive_json()

    assert message["jsonrpc"] == "2.0"
    assert message["id"] == 10
    result = message["result"]
    assert result["structuredContent"]["metadata"]["tool"] == "getLeads"
    assert result["structuredContent"]["result"]["result"][0]["ID"] == "77"
    assert result["content"][0]["type"] == "text"
