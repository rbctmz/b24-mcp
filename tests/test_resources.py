from __future__ import annotations

import json
from typing import Dict

from fastapi.testclient import TestClient


def test_resource_query_deals(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.deal.list"] = {
        "result": [{"ID": "1", "TITLE": "Test deal"}],
        "total": 1,
    }
    app.state.bitrix_client.responses["crm.dealcategory.list"] = {"result": []}
    app.state.bitrix_client.responses["crm.dealcategory.stage.list"] = {"result": []}

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


def test_resource_query_unfiltered_limit_default(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.lead.list"] = {"result": []}

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/leads", "params": {"select": ["ID"]}},
    )

    assert response.status_code == 200
    assert app.state.bitrix_client.calls[0][0] == "crm.lead.list"
    assert app.state.bitrix_client.calls[0][1]["limit"] == 5


def test_resource_query_unfiltered_limit_respects_explicit(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.lead.list"] = {"result": []}

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/leads", "params": {"select": ["ID"], "limit": 20}},
    )

    assert response.status_code == 200
    assert app.state.bitrix_client.calls[0][0] == "crm.lead.list"
    assert app.state.bitrix_client.calls[0][1]["limit"] == 20


def test_resource_query_unfiltered_limit_skipped_when_filter_present(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.lead.list"] = {"result": []}

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/leads", "params": {"select": ["ID"], "filter": {"STATUS_ID": "NEW"}}},
    )

    assert response.status_code == 200
    assert app.state.bitrix_client.calls[0][0] == "crm.lead.list"
    assert "limit" not in app.state.bitrix_client.calls[0][1]


def test_resource_lead_statuses(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.status.list"] = {
        "result": [
            {"STATUS_ID": "NEW", "NAME": "Новый", "SEMANTICS": "process"},
            {"STATUS_ID": "CONVERTED", "NAME": "Сконвертирован", "SEMANTICS": "success"},
        ],
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/lead_statuses", "params": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["resource"] == "crm/lead_statuses"
    assert body["data"][0]["STATUS_ID"] == "NEW"
    assert body["data"][0]["group"] == "process"
    assert body["data"][0]["groupName"] == "В работе"
    assert app.state.bitrix_client.calls[0] == ("crm.status.list", {"filter": {"ENTITY_ID": "STATUS"}})

    response = client.post(
        "/mcp/resource/query",
        json={
            "resource": "crm/lead_statuses",
            "params": {"filter": {"STATUS_ID": "CONVERTED"}},
        },
    )

    assert response.status_code == 200
    assert app.state.bitrix_client.calls[1] == (
        "crm.status.list",
        {"filter": {"STATUS_ID": "CONVERTED", "ENTITY_ID": "STATUS"}},
    )


def test_resource_lead_statuses_caching(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.status.list"] = {
        "result": [{"STATUS_ID": "NEW", "NAME": "Новый"}],
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/lead_statuses", "params": {}},
    )
    assert response.status_code == 200
    assert len(app.state.bitrix_client.calls) == 1

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/lead_statuses", "params": {}},
    )
    assert response.status_code == 200
    assert len(app.state.bitrix_client.calls) == 1


def test_resource_lead_sources(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.status.list"] = {
        "result": [
            {"ID": "CALL", "NAME": "Звонок"},
            {"ID": "ADVERTISING", "NAME": "Реклама"},
        ],
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/lead_sources", "params": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["resource"] == "crm/lead_sources"
    assert body["data"][1]["ID"] == "ADVERTISING"
    assert app.state.bitrix_client.calls[0] == ("crm.status.list", {"filter": {"ENTITY_ID": "SOURCE"}})


def test_resource_lead_sources_custom_filter(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.status.list"] = {
        "result": [{"ID": "SELF", "NAME": "Существующий клиент"}],
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/lead_sources", "params": {"filter": {"ID": "SELF"}}},
    )

    assert response.status_code == 200
    assert app.state.bitrix_client.calls[0] == (
        "crm.status.list",
        {"filter": {"ID": "SELF", "ENTITY_ID": "SOURCE"}},
    )


def test_resource_lead_sources_caching(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.status.list"] = {
        "result": [{"ID": "SELF", "NAME": "Существующий клиент"}],
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/lead_sources", "params": {}},
    )
    assert response.status_code == 200
    assert len(app.state.bitrix_client.calls) == 1

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/lead_sources", "params": {}},
    )
    assert response.status_code == 200
    assert len(app.state.bitrix_client.calls) == 1


def test_resource_deal_categories(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.dealcategory.list"] = {
        "result": [
            {"ID": 0, "NAME": "Основная"},
            {"ID": 3, "NAME": "Продажи"},
        ]
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/deal_categories", "params": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["resource"] == "crm/deal_categories"
    assert body["data"][1]["ID"] == 3
    assert app.state.bitrix_client.calls[0] == ("crm.dealcategory.list", {})


def test_resource_deal_categories_caching(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.dealcategory.list"] = {
        "result": [{"ID": 0, "NAME": "Основная"}],
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/deal_categories", "params": {}},
    )
    assert response.status_code == 200
    assert len(app.state.bitrix_client.calls) == 1

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/deal_categories", "params": {}},
    )
    assert response.status_code == 200
    assert len(app.state.bitrix_client.calls) == 1


def test_resource_deal_stages_default_category(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.dealcategory.stage.list"] = {
        "result": [
            {"ID": "NEW", "NAME": "Новая", "CATEGORY_ID": 0, "SEMANTICS": "process"},
        ]
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/deal_stages", "params": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["resource"] == "crm/deal_stages"
    assert body["data"][0]["ID"] == "NEW"
    assert app.state.bitrix_client.calls[0] == ("crm.dealcategory.stage.list", {"id": 0})


def test_resource_deal_stages_with_category_alias(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.dealcategory.stage.list"] = {
        "result": [
            {"ID": "WON", "NAME": "Успешно", "CATEGORY_ID": 3, "SEMANTICS": "success"},
        ]
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/deal_stages", "params": {"categoryId": 3}},
    )

    assert response.status_code == 200
    assert app.state.bitrix_client.calls[0] == ("crm.dealcategory.stage.list", {"id": 3})


def test_resource_task_statuses(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["tasks.task.getFields"] = {
        "result": {
            "STATUS": {
                "type": "enumeration",
                "items": [
                    {"ID": "1", "NAME": "Новая"},
                    {"ID": "5", "NAME": "Завершена"},
                ],
            }
        }
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "tasks/statuses", "params": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["resource"] == "tasks/statuses"
    assert body["data"][0]["ID"] == "1"
    assert app.state.bitrix_client.calls[0] == ("tasks.task.getFields", {})


def test_resource_task_statuses_caching(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["tasks.task.getFields"] = {
        "result": {
            "STATUS": {
                "type": "enumeration",
                "items": [
                    {"ID": "1", "NAME": "Новая"},
                ],
            }
        }
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "tasks/statuses", "params": {}},
    )
    assert response.status_code == 200
    assert len(app.state.bitrix_client.calls) == 1

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "tasks/statuses", "params": {}},
    )
    assert response.status_code == 200
    assert len(app.state.bitrix_client.calls) == 1


def test_resource_task_statuses_enumeration_dict(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["tasks.task.getFields"] = {
        "result": {"STATUS": {"type": "enumeration", "values": {"1": {"NAME": "Новая"}, "5": {"NAME": "Завершена"}}}}
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "tasks/statuses", "params": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert {item["ID"] for item in body["data"]} == {"1", "5"}
    assert any(item.get("NAME") == "Завершена" for item in body["data"])


def test_resource_task_statuses_nested_fields_labels(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["tasks.task.getFields"] = {
        "result": {
            "fields": {
                "STATUS": {
                    "type": "enumeration",
                    "labels": {
                        "1": "Новая",
                        "2": "В работе",
                    },
                }
            }
        }
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "tasks/statuses", "params": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert {item["ID"] for item in body["data"]} == {"1", "2"}
    assert any(item.get("NAME") == "В работе" for item in body["data"])


def test_resource_task_priorities(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["tasks.task.getFields"] = {
        "result": {
            "PRIORITY": {
                "type": "enumeration",
                "values": {"0": {"NAME": "Низкий"}, "2": {"NAME": "Высокий"}},
            }
        }
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "tasks/priorities", "params": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["resource"] == "tasks/priorities"
    assert {item["ID"] for item in body["data"]} == {"0", "2"}
    assert app.state.bitrix_client.calls[0] == ("tasks.task.getFields", {})


def test_resource_task_priorities_caching(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["tasks.task.getFields"] = {
        "result": {"PRIORITY": {"type": "enumeration", "labels": {"0": "Низкий"}}}
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "tasks/priorities", "params": {}},
    )
    assert response.status_code == 200
    assert len(app.state.bitrix_client.calls) == 1

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "tasks/priorities", "params": {}},
    )
    assert response.status_code == 200
    assert len(app.state.bitrix_client.calls) == 1


def test_leads_enriched_meta(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.lead.list"] = {
        "result": [
            {
                "ID": "11",
                "ASSIGNED_BY_ID": 101,
                "CREATED_BY_ID": 202,
                "MODIFY_BY_ID": 303,
                "STATUS_ID": "NEW",
                "SOURCE_ID": "CALL",
                "CURRENCY_ID": "USD",
            }
        ]
    }

    def status_list(payload: Dict[str, Any]) -> Dict[str, Any]:
        entity_id = payload.get("filter", {}).get("ENTITY_ID")
        if entity_id == "STATUS":
            return {"result": [{"STATUS_ID": "NEW", "NAME": "Новый"}]}
        if entity_id == "SOURCE":
            return {"result": [{"ID": "CALL", "NAME": "Звонок"}]}
        raise AssertionError(f"Unexpected ENTITY_ID {entity_id}")

    app.state.bitrix_client.responses["crm.status.list"] = status_list
    app.state.bitrix_client.responses["crm.currency.list"] = {
        "result": [
            {"CURRENCY": "USD", "NAME": "US Dollar"},
        ]
    }

    def user_info(payload: Dict[str, Any]) -> Dict[str, Any]:
        user_id = payload.get("ID")
        names = {
            101: ("Alice", "Smith"),
            202: ("Bob", "Builder"),
            303: ("Carol", "Jones"),
        }
        first, last = names.get(user_id, ("User", str(user_id)))
        return {
            "result": {
                "ID": user_id,
                "NAME": first,
                "LAST_NAME": last,
            }
        }

    app.state.bitrix_client.responses["user.get"] = user_info

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/leads", "params": {"select": ["ID", "ASSIGNED_BY_ID", "STATUS_ID", "SOURCE_ID"]}},
    )

    assert response.status_code == 200
    body = response.json()
    meta = body["data"][0]["_meta"]
    assert meta["responsible"]["name"] == "Alice Smith"
    assert meta["creator"]["name"] == "Bob Builder"
    assert meta["modifier"]["name"] == "Carol Jones"
    assert meta["status"]["name"] == "Новый"
    assert meta["source"]["name"] == "Звонок"
    assert meta["currency"]["name"] == "US Dollar"


def test_deals_enriched_meta(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.deal.list"] = {
        "result": [
            {
                "ID": "5",
                "ASSIGNED_BY_ID": 77,
                "CATEGORY_ID": 3,
                "STAGE_ID": "C3:WON",
            }
        ]
    }

    app.state.bitrix_client.responses["crm.dealcategory.list"] = {
        "result": [
            {"ID": "3", "NAME": "Enterprise"},
        ]
    }

    def stage_list(payload: Dict[str, Any]) -> Dict[str, Any]:
        category_id = payload.get("id")
        if category_id in (3, "3"):
            return {"result": [{"STATUS_ID": "C3:WON", "NAME": "Won"}]}
        return {"result": []}

    app.state.bitrix_client.responses["crm.dealcategory.stage.list"] = stage_list
    app.state.bitrix_client.responses["user.get"] = lambda payload: {
        "result": {
            "ID": payload.get("ID"),
            "NAME": "John",
            "LAST_NAME": "Doe",
        }
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/deals", "params": {"select": ["ID", "CATEGORY_ID", "STAGE_ID", "ASSIGNED_BY_ID"]}},
    )

    assert response.status_code == 200
    body = response.json()
    meta = body["data"][0]["_meta"]
    assert meta["responsible"]["name"] == "John Doe"
    assert meta["category"]["name"] == "Enterprise"
    assert meta["stage"]["name"] == "Won"


def test_tasks_enriched_meta(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["tasks.task.list"] = {
        "result": [
            {
                "ID": "201",
                "RESPONSIBLE_ID": 501,
                "CREATED_BY": 502,
                "STATUS": "5",
                "PRIORITY": "2",
            }
        ]
    }

    app.state.bitrix_client.responses["tasks.task.getFields"] = lambda payload: {
        "result": {
            "STATUS": {
                "items": [
                    {"ID": "5", "NAME": "Завершена"},
                ]
            },
            "PRIORITY": {
                "values": {"2": {"NAME": "Высокий"}},
            },
        }
    }

    app.state.bitrix_client.responses["user.get"] = lambda payload: {
        "result": {
            "ID": payload.get("ID"),
            "NAME": f"User {payload.get('ID')}",
            "LAST_NAME": "Test",
        }
    }

    response = client.post(
        "/mcp/resource/query",
        json={"resource": "crm/tasks", "params": {"select": ["ID", "RESPONSIBLE_ID", "STATUS", "PRIORITY"]}},
    )

    assert response.status_code == 200
    body = response.json()
    meta = body["data"][0]["_meta"]
    assert meta["responsible"]["name"] == "User 501 Test"
    assert meta["creator"]["name"] == "User 502 Test"
    assert meta["status"]["name"] == "Завершена"
    assert meta["priority"]["name"] == "Высокий"


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


def test_resource_release_versions(app, client: TestClient) -> None:
    response = client.post("/mcp/resource/query", json={"resource": "versions/releases", "params": {}})
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["resource"] == "versions/releases"
    assert body["total"] == len(body["data"])
    versions = {entry.get("version") for entry in body["data"]}
    assert "0.1.0" in versions
    alias_response = client.post("/mcp/resource/query", json={"resource": "releases", "params": {}})
    assert alias_response.status_code == 200
    assert alias_response.json()["data"] == body["data"]


def test_mcp_handshake(app, client: TestClient) -> None:
    response = client.post("/mcp", json={"client": "test"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "initialize"
    params = payload["params"]
    assert params["serverInfo"]["name"] == "Bitrix24 MCP Server"
    assert params["protocolVersion"] == "2025-06-18"
    assert "resources" in params["capabilities"]
    assert "tools" in params["capabilities"]
    assert any(resource["uri"] == "crm/deals" for resource in params["resources"])
    assert "structuredInstructions" in params
    assert params["structuredInstructions"][0]["title"] == "Свежие лиды"
    assert "instructionNotes" in params
    assert any("DATE_CREATE" in note for note in params["instructionNotes"])


def test_mcp_initialize_alias(app, client: TestClient) -> None:
    response = client.post("/mcp/initialize", json={"client": "test"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] is None
    params = payload["result"]
    assert params["protocolVersion"] == "2025-06-18"
    assert any(resource["uri"] == "crm/deals" for resource in params["resources"])
    assert params["structuredInstructions"][0]["title"] == "Свежие лиды"


def test_mcp_get_entrypoint(app, client: TestClient) -> None:
    response = client.get("/mcp")

    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "initialize"
    params = payload["params"]
    assert params["protocolVersion"] == "2025-06-18"
    assert any(resource["uri"] == "crm/deals" for resource in params["resources"])
    assert params["structuredInstructions"][0]["order"]["DATE_MODIFY"] == "DESC"


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
    assert any(resource["uri"] == "bitrix24_leads_guide" for resource in resources)


def test_mcp_resources_query_jsonrpc(app, client: TestClient) -> None:
    app.state.bitrix_client.responses["crm.deal.list"] = {
        "result": [{"ID": "1", "TITLE": "JSONRPC Deal"}],
        "total": 1,
    }
    app.state.bitrix_client.responses["crm.dealcategory.list"] = {"result": []}
    app.state.bitrix_client.responses["crm.dealcategory.stage.list"] = {"result": []}

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


def test_leads_guide_resource(app, client: TestClient) -> None:
    response = client.post(
        "/mcp/resource/query",
        json={"resource": "bitrix24_leads_guide", "params": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["resource"] == "bitrix24_leads_guide"
    scenarios = body["data"]
    assert any(item["type"] == "scenario" for item in scenarios)
    assert any(item.get("type") == "rules" for item in scenarios)


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
