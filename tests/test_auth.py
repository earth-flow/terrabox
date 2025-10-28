#!/usr/bin/env python3
"""Pytest test suite for authentication system."""

import pytest
import requests
import json
from datetime import datetime
from typing import Dict, Any, Optional, Tuple


@pytest.fixture(scope="session")
def base_url():
    """Base URL for the API."""
    return "http://localhost:8000"


@pytest.fixture
def test_user_data():
    """Generate unique test user data for each test."""
    import time
    return {
        "email": f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000000) % 1000000}@example.com",
        "password": "Testpassword123"
    }


@pytest.fixture
def registered_user(base_url, test_user_data):
    """Register a test user and return user response and data."""
    response = requests.post(
        f"{base_url}/v1/register",
        json=test_user_data
    )
    assert response.status_code == 201
    return response.json(), test_user_data


@pytest.fixture
def auth_token(base_url, registered_user):
    """Login and return authentication token."""
    user_response, user_data = registered_user
    login_data = {
        "email": user_data["email"],
        "password": user_data["password"]
    }
    
    response = requests.post(
        f"{base_url}/v1/login",
        json=login_data
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def api_key_data(base_url, auth_token):
    """Create an API key and return key data."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    api_key_data = {
        "label": f"Test API Key {datetime.now().strftime('%Y%m%d_%H%M%S')}"
    }
    
    response = requests.post(
        f"{base_url}/v1/gui/api-keys",
        json=api_key_data,
        headers=headers
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def fresh_user_data():
    """Generate fresh user data specifically for registration tests."""
    import time
    return {
        "email": f"fresh_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000000) % 1000000}@example.com",
        "password": "Testpassword123"
    }


class TestHealthCheck:
    """Test basic health check functionality."""
    
    def test_health_check(self, base_url):
        """Test basic health check endpoint."""
        response = requests.get(f"{base_url}/")
        assert response.status_code == 200
        assert "message" in response.json() or "status" in response.json()

class TestAuthentication:
    """Test user authentication functionality."""
    
    def test_user_registration(self, base_url, fresh_user_data):
        """Test user registration."""
        response = requests.post(
            f"{base_url}/v1/register",
            json=fresh_user_data
        )
        assert response.status_code == 201
        response_data = response.json()
        assert "user_id" in response_data
        assert "email" in response_data

    def test_user_login(self, base_url, registered_user):
        """Test user login."""
        user_response, user_data = registered_user
        login_data = {
            "email": user_data["email"],
            "password": user_data["password"]
        }
        
        response = requests.post(
            f"{base_url}/v1/login",
            json=login_data
        )
        assert response.status_code == 200
        response_data = response.json()
        assert "access_token" in response_data
        assert "token_type" in response_data

    def test_get_current_user(self, base_url, auth_token):
        """Test getting current user info."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.get(
            f"{base_url}/v1/gui/me",
            headers=headers
        )
        assert response.status_code == 200
        response_data = response.json()
        assert "email" in response_data

class TestAPIKeys:
    """Test API key management functionality."""
    
    def test_create_api_key(self, base_url, auth_token):
        """Test creating API key."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        api_key_data = {
            "label": f"Test API Key {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        }
        
        response = requests.post(
            f"{base_url}/v1/gui/api-keys",
            json=api_key_data,
            headers=headers
        )
        assert response.status_code == 201
        response_data = response.json()
        assert "key" in response_data
        assert "id" in response_data
        assert "label" in response_data

    def test_list_api_keys(self, base_url, auth_token, api_key_data):
        """Test listing API keys."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.get(
            f"{base_url}/v1/gui/api-keys",
            headers=headers
        )
        assert response.status_code == 200
        response_data = response.json()
        assert isinstance(response_data, list)
        assert len(response_data) > 0

    def test_revoke_api_key(self, base_url, auth_token):
        """Test revoking (deactivating) an API key."""
        # Create a new API key for this test
        headers = {"Authorization": f"Bearer {auth_token}"}
        api_key_data = {
            "label": f"Test API Key for Revoke {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        }
        
        create_response = requests.post(
            f"{base_url}/v1/gui/api-keys",
            json=api_key_data,
            headers=headers
        )
        assert create_response.status_code == 201
        api_key_id = create_response.json()["id"]
        
        # Now revoke it
        response = requests.delete(
            f"{base_url}/v1/gui/api-keys/{api_key_id}",
            headers=headers
        )
        assert response.status_code == 204

    def test_remove_active_api_key_should_fail(self, base_url, auth_token):
        """Test that removing an active API key should fail."""
        # Create a new API key for this test
        headers = {"Authorization": f"Bearer {auth_token}"}
        api_key_data = {
            "label": f"Test API Key for Remove Fail {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        }
        
        create_response = requests.post(
            f"{base_url}/v1/gui/api-keys",
            json=api_key_data,
            headers=headers
        )
        assert create_response.status_code == 201
        api_key_id = create_response.json()["id"]
        
        # Try to remove active API key (should fail)
        response = requests.delete(
            f"{base_url}/v1/gui/api-keys/{api_key_id}/remove",
            headers=headers
        )
        assert response.status_code == 400

    def test_remove_deactivated_api_key(self, base_url, auth_token):
        """Test permanently removing a deactivated API key."""
        # Create a new API key for this test
        headers = {"Authorization": f"Bearer {auth_token}"}
        api_key_data = {
            "label": f"Test API Key for Remove {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        }
        
        create_response = requests.post(
            f"{base_url}/v1/gui/api-keys",
            json=api_key_data,
            headers=headers
        )
        assert create_response.status_code == 201
        api_key_id = create_response.json()["id"]
        
        # First revoke it
        revoke_response = requests.delete(
            f"{base_url}/v1/gui/api-keys/{api_key_id}",
            headers=headers
        )
        assert revoke_response.status_code == 204
        
        # Now remove it
        response = requests.delete(
            f"{base_url}/v1/gui/api-keys/{api_key_id}/remove",
            headers=headers
        )
        assert response.status_code == 204

class TestTools:
    """Test tool management and execution functionality."""
    
    def test_list_toolkits(self, base_url, api_key_data):
        """Test listing available toolkits."""
        headers = {"X-API-Key": api_key_data["key"]}
        
        response = requests.get(
            f"{base_url}/v1/sdk/toolkits",
            headers=headers
        )
        assert response.status_code == 200
        toolkits = response.json()
        assert isinstance(toolkits, list)

    def test_list_all_tools(self, base_url, api_key_data):
        """Test listing all available tools."""
        headers = {"X-API-Key": api_key_data["key"]}
        
        response = requests.get(
            f"{base_url}/v1/sdk/tools",
            headers=headers
        )
        assert response.status_code == 200
        tools = response.json()
        assert isinstance(tools, list)

    def test_list_tools_by_toolkit(self, base_url, api_key_data):
        """Test listing tools for a specific toolkit."""
        headers = {"X-API-Key": api_key_data["key"]}
        
        # First get available toolkits
        toolkits_response = requests.get(
            f"{base_url}/v1/sdk/toolkits",
            headers=headers
        )
        assert toolkits_response.status_code == 200
        toolkits = toolkits_response.json()
        
        if toolkits:
            toolkit_name = toolkits[0]["name"]
            params = {"toolkit": toolkit_name}
            
            response = requests.get(
                f"{base_url}/v1/sdk/tools",
                headers=headers,
                params=params
            )
            assert response.status_code == 200
            tools = response.json()
            assert isinstance(tools, list)

    def test_get_tool_detail(self, base_url, api_key_data):
        """Test getting tool detail."""
        headers = {"X-API-Key": api_key_data["key"]}
        
        # First get available tools
        tools_response = requests.get(
            f"{base_url}/v1/sdk/tools",
            headers=headers
        )
        assert tools_response.status_code == 200
        tools = tools_response.json()
        
        if tools:
            tool_slug = tools[0]["slug"]
            response = requests.get(
                f"{base_url}/v1/sdk/tools/{tool_slug}",
                headers=headers
            )
            assert response.status_code == 200
            tool_detail = response.json()
            assert "slug" in tool_detail

    @pytest.mark.parametrize("tool_slug,arguments", [
        ("example.echo", {"message": "Hello from test!"}),
        ("example.math_add", {"a": 5, "b": 3}),
    ])
    def test_execute_example_tools(self, base_url, api_key_data, registered_user, tool_slug, arguments):
        """Test executing example tools."""
        user_response, _ = registered_user
        headers = {"X-API-Key": api_key_data["key"]}
        
        payload = {
            "inputs": arguments,
            "metadata": {
                "user_id": user_response["user_id"]
            }
        }
        
        response = requests.post(
            f"{base_url}/v1/sdk/tools/{tool_slug}/execute",
            json=payload,
            headers=headers
        )
        # Note: These tools may not be available, so we check for either success or 404
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            result = response.json()
            assert "success" in result

class TestConnections:
    """Test connection management functionality."""
    
    @pytest.mark.parametrize("toolkit", ["github"])
    def test_create_connection(self, base_url, api_key_data, toolkit):
        """Test creating OAuth connection."""
        headers = {"X-API-Key": api_key_data["key"]}
        
        payload = {
            "name": f"{toolkit} Connection",
            "auth_method": "oauth2",
            "credentials": {},
            "scopes": []
        }
        
        response = requests.post(
            f"{base_url}/v1/sdk/toolkits/{toolkit}/connections",
            json=payload,
            headers=headers
        )
        # Connection creation may not be available in test environment
        assert response.status_code in [201, 404, 400]
        
        if response.status_code == 201:
            connection_data = response.json()
            assert "id" in connection_data

    def test_get_connection_status(self, base_url, api_key_data):
        """Test getting connection status."""
        headers = {"X-API-Key": api_key_data["key"]}
        
        # First try to create a connection to test with
        payload = {
            "name": "Test Connection",
            "auth_method": "oauth2",
            "credentials": {},
            "scopes": []
        }
        
        create_response = requests.post(
            f"{base_url}/v1/sdk/toolkits/github/connections",
            json=payload,
            headers=headers
        )
        
        if create_response.status_code == 201:
            connection_id = create_response.json()["id"]
            
            response = requests.get(
                f"{base_url}/v1/sdk/connections/{connection_id}",
                headers=headers
            )
            assert response.status_code == 200
            connection_status = response.json()
            assert "status" in connection_status

    @pytest.mark.parametrize("toolkit", ["github"])
    def test_list_connected_accounts(self, base_url, api_key_data, toolkit):
        """Test listing connections for a toolkit."""
        headers = {"X-API-Key": api_key_data["key"]}
        
        response = requests.get(
            f"{base_url}/v1/sdk/toolkits/{toolkit}/connections",
            headers=headers
        )
        # May return empty list or 404 if no connections exist
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            connections = response.json()
            assert isinstance(connections, list)

class TestIntegration:
    """Integration tests for the complete workflow."""
    
    @pytest.mark.integration
    def test_complete_workflow(self, base_url, api_key_data, registered_user):
        """Test complete tools and connections workflow."""
        user_response, _ = registered_user
        headers = {"X-API-Key": api_key_data["key"]}
        
        # 1. Test toolkits listing
        toolkits_response = requests.get(
            f"{base_url}/v1/sdk/toolkits",
            headers=headers
        )
        assert toolkits_response.status_code == 200
        toolkits = toolkits_response.json()
        
        # 2. Test tools listing
        tools_response = requests.get(
            f"{base_url}/v1/sdk/tools",
            headers=headers
        )
        assert tools_response.status_code == 200
        tools = tools_response.json()
        
        # 3. Test tool details for available tools
        if tools:
            for tool in tools[:2]:  # Test first 2 tools to avoid spam
                tool_slug = tool["slug"]
                detail_response = requests.get(
                    f"{base_url}/v1/sdk/tools/{tool_slug}",
                    headers=headers
                )
                assert detail_response.status_code == 200
        
        # 4. Test GitHub tool execution (may not be available)
        github_tool_payload = {
            "inputs": {"username": "testuser"},
            "metadata": {"user_id": user_response["user_id"]}
        }
        
        github_response = requests.post(
            f"{base_url}/v1/sdk/tools/github.list_user_repos/execute",
            json=github_tool_payload,
            headers=headers
        )
        # Tool may not be available, so we accept 404
        assert github_response.status_code in [200, 404]
        
        # 5. Test connection creation for GitHub (may not be available)
        connection_payload = {
            "name": "Test GitHub Connection",
            "auth_method": "oauth2",
            "credentials": {},
            "scopes": []
        }
        
        connection_response = requests.post(
            f"{base_url}/v1/sdk/toolkits/github/connections",
            json=connection_payload,
            headers=headers
        )
        # Connection creation may not be available in test environment
        assert connection_response.status_code in [201, 404, 400]


# Pytest markers for test categorization
pytestmark = [
    pytest.mark.auth,
    pytest.mark.api
]