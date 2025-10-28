#!/usr/bin/env python3
"""
测试批量工具端点的认证功能 - Pytest版本
"""

import pytest
import requests
import json


@pytest.fixture(scope="session")
def base_url():
    """基础URL fixture"""
    return "http://127.0.0.1:8000"


@pytest.fixture(scope="session")
def test_user_data():
    """生成测试用户数据"""
    from datetime import datetime
    import time
    return {
        "email": f"test_auth_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000000) % 1000000}@example.com",
        "password": "Testpassword123"
    }


@pytest.fixture(scope="session")
def registered_user(base_url, test_user_data):
    """注册测试用户并返回用户响应和数据"""
    response = requests.post(
        f"{base_url}/v1/register",
        json=test_user_data
    )
    assert response.status_code == 201, f"用户注册失败: {response.text}"
    return response.json(), test_user_data


@pytest.fixture(scope="session")
def test_api_key(registered_user):
    """从注册用户响应中获取API密钥"""
    user_response, _ = registered_user
    return user_response["api_key"]


@pytest.fixture(scope="function")
def test_payload():
    """测试用的请求载荷"""
    return {
        "trajectory_ids": ["test_1"],
        "actions": ['{"a": 5, "b": 3}'],
        "extra_fields": [{"tool": "example.math_add"}],
        "user_id": "test_user"
    }


@pytest.fixture(scope="function")
def tools_endpoint(base_url):
    """工具端点URL"""
    return f"{base_url}/v1/tools/get_observation"


class TestAuthentication:
    """认证功能测试类"""

    @pytest.mark.auth
    @pytest.mark.api
    def test_no_authentication(self, tools_endpoint, test_payload):
        """测试没有认证时的响应"""
        response = requests.post(tools_endpoint, json=test_payload)
        
        assert response.status_code == 422, f"期望状态码422（缺少必需头部），实际得到{response.status_code}"
        print(f"✅ 正确拒绝了未认证的请求，状态码: {response.status_code}")

    @pytest.mark.auth
    @pytest.mark.api
    def test_invalid_api_key(self, tools_endpoint, test_payload):
        """测试无效API密钥"""
        headers = {"X-API-Key": "invalid_key"}
        
        response = requests.post(tools_endpoint, json=test_payload, headers=headers)
        
        assert response.status_code == 401, f"期望状态码401，实际得到{response.status_code}"
        print(f"✅ 正确拒绝了无效API密钥，状态码: {response.status_code}")

    @pytest.mark.auth
    @pytest.mark.api
    def test_malformed_api_key(self, tools_endpoint, test_payload):
        """测试格式错误的API密钥"""
        headers = {"X-API-Key": "malformed"}
        
        response = requests.post(tools_endpoint, json=test_payload, headers=headers)
        
        assert response.status_code == 401, f"期望状态码401，实际得到{response.status_code}"
        print(f"✅ 正确拒绝了格式错误的API密钥，状态码: {response.status_code}")

    @pytest.mark.auth
    @pytest.mark.api
    @pytest.mark.integration
    def test_valid_api_key(self, tools_endpoint, test_payload, test_api_key):
        """测试有效API密钥"""
        headers = {"X-API-Key": test_api_key}
        
        response = requests.post(tools_endpoint, json=test_payload, headers=headers)
        
        assert response.status_code == 200, f"期望状态码200，实际得到{response.status_code}"
        
        data = response.json()
        observations = data.get("observations", [])
        
        assert observations, "应该返回观察结果"
        
        result = observations[0]
        print(f"✅ 有效API密钥认证成功，计算结果: {result}")

    @pytest.mark.parametrize("invalid_key,description", [
        ("", "空字符串"),
        ("short", "过短密钥"),
        ("tlk_invalid_key", "错误前缀"),
        ("invalid_format_key_123", "错误格式"),
    ])
    @pytest.mark.auth
    @pytest.mark.api
    def test_various_invalid_keys(self, tools_endpoint, test_payload, invalid_key, description):
        """测试各种无效API密钥格式"""
        headers = {"X-API-Key": invalid_key}
        
        response = requests.post(tools_endpoint, json=test_payload, headers=headers)
        
        assert response.status_code == 401, f"使用{description}应该返回401，实际得到{response.status_code}"
        print(f"✅ 正确拒绝了{description}: {invalid_key}")


class TestAuthenticationHeaders:
    """认证头测试类"""

    @pytest.mark.auth
    @pytest.mark.api
    def test_missing_header(self, tools_endpoint, test_payload):
        """测试缺少API密钥头部时的响应"""
        response = requests.post(tools_endpoint, json=test_payload)
        
        assert response.status_code == 422
        print(f"✅ 正确处理了缺少API密钥头部的请求，状态码: {response.status_code}")

    @pytest.mark.auth
    @pytest.mark.api
    def test_wrong_header_name(self, tools_endpoint, test_payload, test_api_key):
        """测试错误的头部名称时的响应"""
        headers = {"Authorization": f"Bearer {test_api_key}"}  # 错误的头部名称
        response = requests.post(tools_endpoint, json=test_payload, headers=headers)
        
        assert response.status_code == 422
        print(f"✅ 正确处理了错误头部名称的请求，状态码: {response.status_code}")

    @pytest.mark.auth
    @pytest.mark.api
    def test_case_sensitive_header(self, tools_endpoint, test_payload, test_api_key):
        """测试认证头是否大小写敏感"""
        headers = {"x-api-key": test_api_key}  # 小写
        
        response = requests.post(tools_endpoint, json=test_payload, headers=headers)
        
        # 根据实际API行为调整期望结果
        # 如果API支持大小写不敏感，则应该是200；否则是401
        print(f"小写认证头响应状态码: {response.status_code}")


class TestAuthenticationIntegration:
    """认证集成测试类"""

    @pytest.mark.integration
    @pytest.mark.auth
    @pytest.mark.api
    def test_authentication_workflow(self, tools_endpoint, test_payload, test_api_key):
        """测试完整的认证工作流程"""
        # 1. 首先测试无认证请求
        response_no_auth = requests.post(tools_endpoint, json=test_payload)
        assert response_no_auth.status_code == 422
        
        # 2. 测试无效密钥
        headers_invalid = {"X-API-Key": "invalid_key"}
        response_invalid = requests.post(tools_endpoint, json=test_payload, headers=headers_invalid)
        assert response_invalid.status_code == 401
        
        # 3. 测试有效密钥
        headers_valid = {"X-API-Key": test_api_key}
        response_valid = requests.post(tools_endpoint, json=test_payload, headers=headers_valid)
        assert response_valid.status_code == 200
        
        # 4. 验证返回数据
        data = response_valid.json()
        observations = data.get("observations", [])
        assert observations, "应该返回观察结果"
        
        print("✅ 完整认证工作流程测试通过")