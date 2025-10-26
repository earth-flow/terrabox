#!/usr/bin/env python3
"""
测试批量工具端点的认证功能
"""

import requests
import json

# 用户提供的API密钥
TEST_API_KEY = "tlk_live_DnG-iRaL5iPOa0emw5sF0Nu9O5bG3CSVDw7ivp5y-3Q"
BASE_URL = "http://127.0.0.1:8000"

def test_no_authentication():
    """测试没有认证时的响应"""
    print("🧪 测试: 没有认证头的请求")
    
    payload = {
        "trajectory_ids": ["test_1"],
        "actions": ['{"a": 5, "b": 3}'],
        "extra_fields": [{"tool": "example.math_add"}],
        "user_id": "test_user"
    }
    
    response = requests.post(f"{BASE_URL}/v1/tools/get_observation", json=payload)
    
    print(f"   状态码: {response.status_code}")
    print(f"   响应: {response.text}")
    
    if response.status_code == 401:
        print("   ✅ 正确拒绝了未认证的请求")
        return True
    else:
        print("   ❌ 应该返回401状态码")
        return False

def test_invalid_api_key():
    """测试无效API密钥"""
    print("\n🧪 测试: 无效API密钥")
    
    payload = {
        "trajectory_ids": ["test_1"],
        "actions": ['{"a": 5, "b": 3}'],
        "extra_fields": [{"tool": "example.math_add"}],
        "user_id": "test_user"
    }
    
    headers = {"X-API-Key": "invalid_key"}
    
    response = requests.post(f"{BASE_URL}/v1/tools/get_observation", json=payload, headers=headers)
    
    print(f"   状态码: {response.status_code}")
    print(f"   响应: {response.text}")
    
    if response.status_code == 401:
        print("   ✅ 正确拒绝了无效API密钥")
        return True
    else:
        print("   ❌ 应该返回401状态码")
        return False

def test_valid_api_key():
    """测试有效API密钥"""
    print("\n🧪 测试: 有效API密钥")
    
    payload = {
        "trajectory_ids": ["test_1"],
        "actions": ['{"a": 5, "b": 3}'],
        "extra_fields": [{"tool": "example.math_add"}],
        "user_id": "test_user"
    }
    
    headers = {"X-API-Key": TEST_API_KEY}
    
    response = requests.post(f"{BASE_URL}/v1/tools/get_observation", json=payload, headers=headers)
    
    print(f"   状态码: {response.status_code}")
    print(f"   响应: {response.text}")
    
    if response.status_code == 200:
        data = response.json()
        observations = data.get("observations", [])
        if observations:
            result = observations[0]
            print(f"   计算结果: {result}")
            print("   ✅ 有效API密钥认证成功")
            return True
        else:
            print("   ❌ 没有返回观察结果")
            return False
    else:
        print("   ❌ 认证失败")
        return False

def test_malformed_api_key():
    """测试格式错误的API密钥"""
    print("\n🧪 测试: 格式错误的API密钥")
    
    payload = {
        "trajectory_ids": ["test_1"],
        "actions": ['{"a": 5, "b": 3}'],
        "extra_fields": [{"tool": "example.math_add"}],
        "user_id": "test_user"
    }
    
    headers = {"X-API-Key": "malformed"}
    
    response = requests.post(f"{BASE_URL}/v1/tools/get_observation", json=payload, headers=headers)
    
    print(f"   状态码: {response.status_code}")
    print(f"   响应: {response.text}")
    
    if response.status_code == 401:
        print("   ✅ 正确拒绝了格式错误的API密钥")
        return True
    else:
        print("   ❌ 应该返回401状态码")
        return False

def main():
    """运行所有认证测试"""
    print("🚀 开始批量工具端点认证测试")
    print("=" * 50)
    
    tests = [
        test_no_authentication,
        test_invalid_api_key,
        test_malformed_api_key,
        test_valid_api_key
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"   ❌ 测试异常: {e}")
            results.append(False)
    
    print("\n" + "=" * 50)
    print("📊 认证测试结果汇总:")
    print(f"   通过: {sum(results)}/{len(results)}")
    print(f"   成功率: {sum(results)/len(results)*100:.1f}%")
    
    if all(results):
        print("🎉 所有认证测试通过！")
    else:
        print("⚠️  部分认证测试失败")

if __name__ == "__main__":
    main()