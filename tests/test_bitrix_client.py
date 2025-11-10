from mcp_server.app.bitrix_client import (
    is_incoming_webhook_base_url,
    payload_with_auth,
)


def test_payload_with_auth_adds_token_when_enabled() -> None:
    original = {"foo": "bar"}
    result = payload_with_auth(original, "token", include_auth=True)
    assert result is not original
    assert result["foo"] == "bar"
    assert result["auth"] == "token"


def test_payload_with_auth_skips_when_disabled() -> None:
    original = {"foo": "bar"}
    result = payload_with_auth(original, "token", include_auth=False)
    assert result is original
    assert "auth" not in result


def test_payload_with_auth_skips_when_token_missing() -> None:
    original = {"foo": "bar"}
    result = payload_with_auth(original, None)
    assert result is original
    assert "auth" not in result


def test_is_incoming_webhook_base_url_detects_webhook() -> None:
    assert is_incoming_webhook_base_url("https://example.com/rest/1/abc123")


def test_is_incoming_webhook_base_url_regular_rest() -> None:
    assert not is_incoming_webhook_base_url("https://example.com/rest")
