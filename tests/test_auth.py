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
        "username": f"testuser_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "email": f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}@example.com",
        "password": "testpassword123"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/v2/auth/register",
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
        "username": user_data["username"],
        "password": user_data["password"]
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/v2/auth/login",
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
            f"{BASE_URL}/v2/auth/me",
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
        "name": f"Test API Key {datetime.now().strftime('%Y%m%d_%H%M%S')}"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/v2/auth/api-keys",
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
            f"{BASE_URL}/v2/auth/api-keys",
            headers=headers
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_verify_api_key(api_key):
    """Test API key verification."""
    print("\n=== Testing API Key Verification ===")
    
    try:
        response = requests.post(
            f"{BASE_URL}/v2/auth/verify-api-key",
            json={"api_key": api_key}
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    """Run all authentication tests."""
    print("Starting Authentication System Tests...")
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
    
    # Test list API keys
    if not test_list_api_keys(token):
        print("❌ List API keys failed")
        return
    
    print("✅ List API keys passed")
    
    # Test verify API key
    if not test_verify_api_key(api_key):
        print("❌ Verify API key failed")
        return
    
    print("✅ Verify API key passed")
    
    print("\n🎉 All authentication tests passed!")
    print(f"\n📝 Test Summary:")
    print(f"   - Created user: {user_data['username']} ({user_data['email']})")
    print(f"   - Generated JWT token: {token[:20]}...")
    print(f"   - Generated API key: {api_key[:20]}...")
    print(f"\n💡 You can now use these credentials to test SDK integration!")

if __name__ == "__main__":
    main()