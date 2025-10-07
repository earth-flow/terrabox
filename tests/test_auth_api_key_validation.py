import pytest
from fastapi.testclient import TestClient

from terralink_platform.main import create_app


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_invalid_api_key_format_rejected(client):
    """使用格式错误的API Key请求应返回401。"""
    headers = {"X-API-Key": "invalid"}
    r = client.get("/v1/sdk/tools", headers=headers)
    assert r.status_code == 401, r.text
    detail = r.json().get("detail")
    assert detail == "Invalid API key format" or detail == "Invalid API key"


def test_unknown_but_well_formatted_api_key_rejected(client):
    """使用格式正确但不存在的API Key应返回401。"""
    unknown_key = "tlk_live_" + ("A" * 32)
    headers = {"X-API-Key": unknown_key}
    r = client.get("/v1/sdk/tools", headers=headers)
    assert r.status_code == 401, r.text
    assert r.json().get("detail") == "Invalid API key"


def test_execute_tool_with_invalid_api_key_rejected(client):
    """执行工具时使用无效API Key应返回401。"""
    unknown_key = "tlk_live_" + ("B" * 32)
    headers = {"X-API-Key": unknown_key}
    body = {"inputs": {"a": 1, "b": 2}, "metadata": {"user_id": "tester"}}
    r = client.post("/v1/sdk/tools/example.math_add/execute", json=body, headers=headers)
    assert r.status_code == 401, r.text
    assert r.json().get("detail") in {"Invalid API key", "Invalid API key format"}