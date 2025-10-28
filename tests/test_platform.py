import json
import pytest
import uuid
from fastapi.testclient import TestClient

from terrakit.main import create_app


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def register(client, email: str, password: str = "Password123") -> str:
    resp = client.post("/v1/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    return resp.json()["api_key"]


def test_full_flow(client):
    # Register a user with unique email
    unique_email = f"alice-{uuid.uuid4()}@example.com"
    api_key = register(client, unique_email)
    headers = {"X-API-Key": api_key}
    # List toolkits
    r = client.get("/v1/sdk/toolkits", headers=headers)
    assert r.status_code == 200
    tk = r.json()
    assert any(t["name"] == "github" for t in tk)
    # List tools (should include our two github tools)
    r = client.get("/v1/sdk/tools", headers=headers)
    assert r.status_code == 200
    tools = r.json()
    slugs = [t["slug"] for t in tools]
    assert "github.list_user_repos" in slugs
    assert "github.create_issue" in slugs
    # Execute list_user_repos without connection (no context yet)
    exec_body = {
        "inputs": {"username": "alice"},
        "metadata": {"user_id": "alice"},
    }
    r = client.post("/v1/sdk/tools/github.list_user_repos/execute", json=exec_body, headers=headers)
    assert r.status_code == 200, f"Response: {r.text}"
    data = r.json()
    print(f"Tool execution response: {data}")  # Debug output
    assert data["success"] is True
    repos = data["outputs"]["repositories"]
    assert len(repos) > 0  # Just check that we got some repositories
    # Execute create_issue without connection should fail
    exec_body2 = {
        "inputs": {"repository": "alice-repo", "title": "Bug", "body": "Details"},
        "metadata": {"user_id": "alice"},
    }
    r = client.post("/v1/sdk/tools/github.create_issue/execute", json=exec_body2, headers=headers)
    assert r.status_code == 409 or not r.json()["success"]
    # Initiate connection for github
    r = client.post("/v1/sdk/toolkits/github/connections", json={"name": "github-connection", "auth_method": "oauth2"}, headers=headers)
    assert r.status_code == 201
    conn_id = r.json()["id"]
    # Poll connection (first call) should authorise and create account
    r = client.get(f"/v1/sdk/connections/{conn_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "valid"
    # Execute create_issue with the connection should succeed
    exec_body3 = {
        "inputs": {"repository": "alice-repo", "title": "New Issue", "body": "Test"},
        "metadata": {"user_id": "alice"},
        "connection_id": conn_id,
    }
    r = client.post("/v1/sdk/tools/github.create_issue/execute", json=exec_body3, headers=headers)
    assert r.status_code == 200
    resp = r.json()
    assert resp["success"] is True
    assert resp["outputs"]["issue_number"]