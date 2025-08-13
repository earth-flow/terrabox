import json
import pytest
from fastapi.testclient import TestClient

from terralink_platform.main import create_app


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def register(client, user_id: str) -> str:
    resp = client.post("/v1/register", json={"user_id": user_id})
    assert resp.status_code == 201, resp.text
    return resp.json()["api_key"]


def test_full_flow(client):
    # Register a user
    api_key = register(client, "alice")
    headers = {"X-API-Key": api_key}
    # List toolkits
    r = client.get("/v1/toolkits", headers=headers)
    assert r.status_code == 200
    tk = r.json()
    assert any(t["name"] == "github" for t in tk)
    # List tools (should include our two github tools)
    r = client.get("/v1/tools", headers=headers)
    assert r.status_code == 200
    tools = r.json()
    slugs = [t["slug"] for t in tools]
    assert "github.list_user_repos" in slugs
    assert "github.create_issue" in slugs
    # Execute list_user_repos without connection (no context yet)
    exec_body = {
        "arguments": {"username": "alice"},
        "context": {"user_id": "alice"},
    }
    r = client.post("/v1/tools/github.list_user_repos/execute", json=exec_body, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    repos = data["data"]["repositories"]
    assert "alice-repo-1" in repos
    # Execute create_issue without connection should fail
    exec_body2 = {
        "arguments": {"repository": "alice-repo", "title": "Bug", "body": "Details"},
        "context": {"user_id": "alice"},
    }
    r = client.post("/v1/tools/github.create_issue/execute", json=exec_body2, headers=headers)
    assert r.status_code == 409 or not r.json()["ok"]
    # Initiate connection for github
    r = client.post("/v1/auth/connections", json={"toolkit": "github", "user_id": "alice"}, headers=headers)
    assert r.status_code == 201
    conn_id = r.json()["connection_id"]
    # Poll connection (first call) should authorise and create account
    r = client.get(f"/v1/auth/connections/{conn_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "authorized"
    acc_id = r.json()["connected_account_id"]
    assert acc_id
    # List connected accounts
    r = client.get("/v1/auth/connected-accounts", params={"user_id": "alice"}, headers=headers)
    assert r.status_code == 200
    accounts = r.json()
    assert accounts[0]["id"] == acc_id
    # Execute create_issue with the connected account should succeed
    exec_body3 = {
        "arguments": {"repository": "alice-repo", "title": "New Issue", "body": "Test"},
        "context": {"user_id": "alice", "connected_account_id": acc_id},
    }
    r = client.post("/v1/tools/github.create_issue/execute", json=exec_body3, headers=headers)
    assert r.status_code == 200
    resp = r.json()
    assert resp["ok"] is True
    assert resp["data"]["issue_number"]
    # Revoke the account
    r = client.delete(f"/v1/auth/connected-accounts/{acc_id}", headers=headers)
    assert r.status_code == 200
    # Ensure account is removed
    r = client.get("/v1/auth/connected-accounts", params={"user_id": "alice"}, headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 0