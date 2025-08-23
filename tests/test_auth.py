#!/usr/bin/env python3
"""Test script for authentication system."""

import requests
import json
from datetime import datetime

# Base URL for the API
BASE_URL = "http://localhost:8000"

def test_health_check():
    """Test basic health check endpoint."""
    print("\n=== Testing Health Check ===")
    try:
        response = requests.get(f"{BASE_URL}/")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_user_registration():
    """Test user registration."""
    print("\n=== Testing User Registration ===")
    
    user_data = {
        "email": f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}@example.com",
        "password": "Testpassword123"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/v1/register",
            json=user_data
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 201:
            return response.json(), user_data
        else:
            return None, user_data
    except Exception as e:
        print(f"Error: {e}")
        return None, user_data

def test_user_login(user_data):
    """Test user login."""
    print("\n=== Testing User Login ===")
    
    login_data = {
        "email": user_data["email"],
        "password": user_data["password"]
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/v1/login",
            json=login_data
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def test_get_current_user(token):
    """Test getting current user info."""
    print("\n=== Testing Get Current User ===")
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.get(
            f"{BASE_URL}/v1/gui/me",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_create_api_key(token):
    """Test creating API key."""
    print("\n=== Testing Create API Key ===")
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    api_key_data = {
        "label": f"Test API Key {datetime.now().strftime('%Y%m%d_%H%M%S')}"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/v1/gui/api-keys",
            json=api_key_data,
            headers=headers
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 201:
            return response.json()
        else:
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def test_list_api_keys(token):
    """Test listing API keys."""
    print("\n=== Testing List API Keys ===")
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.get(
            f"{BASE_URL}/v1/gui/api-keys",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_revoke_api_key(token, api_key_id):
    """Test revoking (deactivating) an API key."""
    print("\n=== Testing Revoke API Key ===")
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.delete(
            f"{BASE_URL}/v1/gui/api-keys/{api_key_id}",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        if response.status_code != 204:
            print(f"Response: {response.text}")
        
        return response.status_code == 204
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_remove_deactivated_api_key(token, api_key_id):
    """Test permanently removing a deactivated API key."""
    print("\n=== Testing Remove Deactivated API Key ===")
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.delete(
            f"{BASE_URL}/v1/gui/api-keys/{api_key_id}/remove",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        if response.status_code != 204:
            print(f"Response: {response.text}")
        
        return response.status_code == 204
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_remove_active_api_key_should_fail(token, api_key_id):
    """Test that removing an active API key should fail."""
    print("\n=== Testing Remove Active API Key (Should Fail) ===")
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.delete(
            f"{BASE_URL}/v1/gui/api-keys/{api_key_id}/remove",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        # Should return 400 Bad Request
        return response.status_code == 400
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_list_toolkits(api_key):
    """Test listing available toolkits."""
    print("\n=== Testing List Toolkits ===")
    
    headers = {"X-API-Key": api_key}
    
    try:
        response = requests.get(
            f"{BASE_URL}/v1/sdk/toolkits",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            toolkits = response.json()
            print(f"Found {len(toolkits)} toolkits")
            return toolkits
        else:
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def test_list_tools(api_key, toolkit=None):
    """Test listing available tools."""
    print(f"\n=== Testing List Tools{' for ' + toolkit if toolkit else ''} ===")
    
    headers = {"X-API-Key": api_key}
    params = {"toolkit": toolkit} if toolkit else {}
    
    try:
        response = requests.get(
            f"{BASE_URL}/v1/sdk/tools",
            headers=headers,
            params=params
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            tools = response.json()
            print(f"Found {len(tools)} tools")
            return tools
        else:
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def test_get_tool_detail(api_key, tool_slug):
    """Test getting tool detail."""
    print(f"\n=== Testing Get Tool Detail: {tool_slug} ===")
    
    headers = {"X-API-Key": api_key}
    
    try:
        response = requests.get(
            f"{BASE_URL}/v1/sdk/tools/{tool_slug}",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_execute_tool(api_key, user_id, tool_slug, arguments):
    """Test executing a tool."""
    print(f"\n=== Testing Execute Tool: {tool_slug} ===")
    
    headers = {"X-API-Key": api_key}
    
    payload = {
        "inputs": arguments,
        "metadata": {
            "user_id": user_id
        }
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/v1/sdk/tools/{tool_slug}/execute",
            json=payload,
            headers=headers
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            result = response.json()
            return result.get("success", False), result
        else:
            return False, None
    except Exception as e:
        print(f"Error: {e}")
        return False, None

def test_create_connection(api_key, user_id, toolkit):
    """Test creating OAuth connection."""
    print(f"\n=== Testing Create Connection for {toolkit} ===")
    
    headers = {"X-API-Key": api_key}
    
    payload = {
        "toolkit": toolkit,
        "user_id": user_id
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/v1/sdk/auth/connections",
            json=payload,
            headers=headers
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 201:
            return response.json()
        else:
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def test_get_connection_status(api_key, connection_id):
    """Test getting connection status."""
    print(f"\n=== Testing Get Connection Status: {connection_id} ===")
    
    headers = {"X-API-Key": api_key}
    
    try:
        response = requests.get(
            f"{BASE_URL}/v1/sdk/auth/connections/{connection_id}",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def test_list_connected_accounts(api_key, user_id, toolkit=None):
    """Test listing connected accounts."""
    print(f"\n=== Testing List Connected Accounts ===")
    
    headers = {"X-API-Key": api_key}
    params = {"user_id": user_id}
    if toolkit:
        params["toolkit"] = toolkit
    
    try:
        response = requests.get(
            f"{BASE_URL}/v1/sdk/auth/connected-accounts",
            headers=headers,
            params=params
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def test_tools_and_connections_workflow(api_key, user_id):
    """Test complete tools and connections workflow."""
    print("\n🔧 === Testing Tools and Connections Workflow ===")
    
    # 1. List toolkits
    toolkits = test_list_toolkits(api_key)
    if not toolkits:
        print("❌ List toolkits failed")
        return False
    print("✅ List toolkits passed")
    
    # 2. List all tools
    all_tools = test_list_tools(api_key)
    if not all_tools:
        print("❌ List all tools failed")
        return False
    print("✅ List all tools passed")
    
    # 3. Test tools by toolkit
    for toolkit in toolkits:
        toolkit_name = toolkit["name"]
        toolkit_tools = test_list_tools(api_key, toolkit_name)
        if toolkit_tools is not None:
            print(f"✅ List tools for {toolkit_name} passed ({len(toolkit_tools)} tools)")
        
        # Test tool details for each tool in this toolkit
        if toolkit_tools:
            for tool in toolkit_tools[:2]:  # Test first 2 tools to avoid spam
                tool_slug = tool["slug"]
                if test_get_tool_detail(api_key, tool_slug):
                    print(f"✅ Get detail for {tool_slug} passed")
    
    # 4. Test executing example tools
    example_tools_to_test = [
        {
            "slug": "example.echo",
            "arguments": {"message": "Hello from test!"}
        },
        {
            "slug": "example.math_add",
            "arguments": {"a": 5, "b": 3}
        },
        {
            "slug": "github.list_user_repos",
            "arguments": {"username": "testuser"}
        }
    ]
    
    for tool_test in example_tools_to_test:
        success, result = test_execute_tool(
            api_key, user_id, tool_test["slug"], tool_test["arguments"]
        )
        if success:
            print(f"✅ Execute {tool_test['slug']} passed")
        else:
            print(f"⚠️ Execute {tool_test['slug']} failed (tool may not be available)")
    
    # 5. Test connection workflow for GitHub
    connection_response = test_create_connection(api_key, user_id, "github")
    if connection_response:
        print("✅ Create GitHub connection passed")
        
        connection_id = connection_response["connection_id"]
        
        # Check connection status (this will auto-authorize in the test implementation)
        status_response = test_get_connection_status(api_key, connection_id)
        if status_response and status_response["status"] == "authorized":
            print("✅ GitHub connection authorized")
            
            # List connected accounts
            accounts = test_list_connected_accounts(api_key, user_id)
            if accounts:
                print(f"✅ List connected accounts passed ({len(accounts)} accounts)")
                
                # Test executing a tool that requires connection
                if accounts:
                    connected_account_id = accounts[0]["id"]
                    success, result = test_execute_tool(
                        api_key, user_id, "github.create_issue",
                        {
                            "repository": "test-repo",
                            "title": "Test Issue",
                            "body": "This is a test issue created by the test suite"
                        }
                    )
                    if success:
                        print("✅ Execute GitHub tool with connection passed")
    
    return True

def main():
    """Run all authentication and tools tests."""
    print("Starting Terralink Platform Tests...")
    print(f"Testing against: {BASE_URL}")
    
    # Test health check
    if not test_health_check():
        print("❌ Health check failed. Is the server running?")
        return
    
    print("✅ Health check passed")
    
    # Test user registration
    user_response, user_data = test_user_registration()
    if not user_response:
        print("❌ User registration failed")
        return
    
    print("✅ User registration passed")
    
    # Test user login
    login_response = test_user_login(user_data)
    if not login_response:
        print("❌ User login failed")
        return
    
    print("✅ User login passed")
    token = login_response["access_token"]
    
    # Test get current user
    if not test_get_current_user(token):
        print("❌ Get current user failed")
        return
    
    print("✅ Get current user passed")
    
    # Test create API key
    api_key_response = test_create_api_key(token)
    if not api_key_response:
        print("❌ Create API key failed")
        return
    
    print("✅ Create API key passed")
    api_key = api_key_response["key"]
    api_key_id = api_key_response["id"]
    
    # Test list API keys
    if not test_list_api_keys(token):
        print("❌ List API keys failed")
        return
    
    print("✅ List API keys passed")
    
    # Create another API key for deletion tests
    api_key_response_2 = test_create_api_key(token)
    if not api_key_response_2:
        print("❌ Create second API key failed")
        return
    
    api_key_id_2 = api_key_response_2["id"]
    
    # Test removing active API key (should fail)
    if not test_remove_active_api_key_should_fail(token, api_key_id_2):
        print("❌ Remove active API key test failed (should have returned 400)")
        return
    
    print("✅ Remove active API key correctly failed")
    
    # Test revoking API key
    if not test_revoke_api_key(token, api_key_id_2):
        print("❌ Revoke API key failed")
        return
    
    print("✅ Revoke API key passed")
    
    # Test removing deactivated API key
    if not test_remove_deactivated_api_key(token, api_key_id_2):
        print("❌ Remove deactivated API key failed")
        return
    
    print("✅ Remove deactivated API key passed")
    
    # 在现有测试完成后添加工具测试
    if api_key_response:
        api_key = api_key_response["key"]
        
        # Test tools and connections workflow
        if test_tools_and_connections_workflow(api_key, user_response["user_id"]):
            print("✅ Tools and connections workflow passed")
        else:
            print("❌ Tools and connections workflow failed")
    
    print("\n🎉 All tests completed!")
    print(f"\n📝 Test Summary:")
    print(f"   - Created user: ({user_data['email']})")
    print(f"   - Generated JWT token: {token[:20]}...")
    print(f"   - Generated API key: {api_key[:20]}...")
    print(f"   - Tested API key revocation and removal")
    print(f"\n💡 You can now use these credentials to test SDK integration!")

if __name__ == "__main__":
    main()