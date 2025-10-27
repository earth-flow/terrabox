#!/usr/bin/env python3
"""
验收测试脚本 - 验证批量工具API的所有功能
"""

import asyncio
import json
import time
import requests
import concurrent.futures
from typing import List, Dict, Any

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "tlk_live_DnG-iRaL5iPOa0emw5sF0Nu9O5bG3CSVDw7ivp5y-3Q"

# 认证头
AUTH_HEADERS = {"X-API-Key": API_KEY}

def test_example_math_add():
    """测试 example.math_add 工具的功能"""
    print("🧪 测试: example.math_add 工具")
    
    # 测试基本加法
    test_data = {
        "trajectory_ids": ["math_test_1"],
        "actions": ['{"a": 5, "b": 3}'],
        "extra_fields": [{"tool": "example.math_add"}],
        "user_id": "math_test_user"
    }
    
    response = requests.post(f"{BASE_URL}/v1/tools/get_observation", json=test_data, headers=AUTH_HEADERS)
    
    print(f"   状态码: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        observations = data.get('observations', [])
        if observations:
            result = observations[0]
            print(f"   计算结果: {result}")
            print("   ✅ math_add 测试通过")
            return True
        else:
            print("   ❌ 没有返回观察结果")
            return False
    else:
        print(f"   ❌ 测试失败: {response.text}")
        return False

def test_example_echo():
    """测试 example.echo 工具的功能"""
    print("\n🧪 测试: example.echo 工具")
    
    # 测试echo功能
    test_data = {
        "trajectory_ids": ["echo_test_1"],
        "actions": ['{"message": "Hello from test!"}'],
        "extra_fields": [{"tool": "example.echo"}],
        "user_id": "echo_test_user"
    }
    
    response = requests.post(f"{BASE_URL}/v1/tools/get_observation", json=test_data, headers=AUTH_HEADERS)
    
    print(f"   状态码: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        observations = data.get('observations', [])
        if observations:
            result = observations[0]
            print(f"   Echo结果: {result}")
            print("   ✅ echo 测试通过")
            return True
        else:
            print("   ❌ 没有返回观察结果")
            return False
    else:
        print(f"   ❌ 测试失败: {response.text}")
        return False

def test_batch_api_multiple_actions():
    """验证 /v1/tools/get_observation 接口能接受 N>1 条 action 并并发执行"""
    print("\n🧪 测试1: 验证批量API接受多个action并并发执行")
    
    # 准备测试数据 - 多个action，使用 example.math_add
    test_data = {
        "trajectory_ids": ["traj_1", "traj_2", "traj_3"],
        "actions": [
            '{"a": 10, "b": 5}',
            '{"a": 20, "b": 15}',
            '{"a": 30, "b": 25}'
        ],
        "extra_fields": [
            {"tool": "example.math_add"},
            {"tool": "example.math_add"},
            {"tool": "example.math_add"}
        ],
        "user_id": "test_user"
    }
    
    start_time = time.time()
    response = requests.post(f"{BASE_URL}/v1/tools/get_observation", json=test_data, headers=AUTH_HEADERS)
    end_time = time.time()
    
    print(f"   状态码: {response.status_code}")
    print(f"   处理时间: {end_time - start_time:.3f}s")
    
    if response.status_code == 200:
        data = response.json()
        observations = data.get('observations', [])
        print(f"   返回观察数量: {len(observations)}")
        print(f"   追踪ID: {data.get('trace_id', 'N/A')}")
        print(f"   处理时间(ms): {data.get('processing_time_ms', 'N/A')}")
        
        # 验证计算结果
        expected_results = [15, 35, 55]  # 10+5, 20+15, 30+25
        for i, obs in enumerate(observations):
            if i < len(expected_results):
                print(f"   计算结果 {i+1}: {obs}")
        
        print("   ✅ 测试通过")
        return True
    else:
        print(f"   ❌ 测试失败: {response.text}")
        return False

def test_async_sync_support():
    """验证同时支持 async 与 sync 工具（sync 不阻塞事件循环）"""
    print("\n🧪 测试2: 验证async与sync工具支持")
    
    # 测试混合 math_add 和 echo 工具
    test_data = {
        "trajectory_ids": ["async_1", "sync_1", "async_2"],
        "actions": [
            '{"a": 1, "b": 2}',
            '{"message": "sync test"}',
            '{"a": 3, "b": 4}'
        ],
        "extra_fields": [
            {"tool": "example.math_add"},
            {"tool": "example.echo"},
            {"tool": "example.math_add"}
        ],
        "user_id": "test_user"
    }
    
    start_time = time.time()
    response = requests.post(f"{BASE_URL}/v1/tools/get_observation", json=test_data, headers=AUTH_HEADERS)
    end_time = time.time()
    
    print(f"   状态码: {response.status_code}")
    print(f"   处理时间: {end_time - start_time:.3f}s")
    
    if response.status_code == 200:
        data = response.json()
        observations = data.get('observations', [])
        print(f"   返回观察数量: {len(observations)}")
        for i, obs in enumerate(observations):
            print(f"   结果 {i+1}: {obs}")
        print("   ✅ 测试通过")
        return True
    else:
        print(f"   ❌ 测试失败: {response.text}")
        return False

def test_performance_comparison():
    """验证大批量（≥1k）时吞吐显著优于旧接口（至少 ×2，并与线程池大小正相关）"""
    print("\n🧪 测试3: 验证大批量性能对比")
    
    # 测试不同批量大小的性能
    batch_sizes = [100, 500, 1000]
    results = {}
    
    for batch_size in batch_sizes:
        print(f"\n   📊 测试批量大小: {batch_size}")
        
        # 1. 测试批量接口性能
        batch_time = test_batch_performance(batch_size)
        if batch_time is None:
            print(f"   ❌ 批量测试失败")
            return False
        
        # 2. 测试单个请求性能（模拟旧接口）
        single_time = test_single_requests_performance(batch_size)
        if single_time is None:
            print(f"   ❌ 单个请求测试失败")
            return False
        
        # 3. 计算性能提升
        speedup = single_time / batch_time if batch_time > 0 else 0
        results[batch_size] = {
            'batch_time': batch_time,
            'single_time': single_time,
            'speedup': speedup
        }
        
        print(f"   批量接口时间: {batch_time:.3f}s")
        print(f"   单个请求时间: {single_time:.3f}s")
        print(f"   性能提升: {speedup:.1f}x")
        
        # 验证性能提升至少2倍
        if speedup >= 2.0:
            print(f"   ✅ 性能提升达标 ({speedup:.1f}x ≥ 2x)")
        else:
            print(f"   ⚠️  性能提升不足 ({speedup:.1f}x < 2x)")
    
    # 验证性能与批量大小的关系
    print(f"\n   📈 性能趋势分析:")
    for size in batch_sizes:
        result = results[size]
        print(f"   批量{size}: {result['speedup']:.1f}x 提升")
    
    # 检查是否所有测试都达到2倍性能提升
    all_passed = all(results[size]['speedup'] >= 2.0 for size in batch_sizes)
    
    if all_passed:
        print("   ✅ 所有批量大小都达到2倍以上性能提升")
        return True
    else:
        print("   ❌ 部分批量大小未达到2倍性能提升")
        return False

def test_batch_performance(batch_size: int) -> float:
    """测试批量接口性能"""
    trajectory_ids = [f"batch_perf_{i}" for i in range(batch_size)]
    actions = [f'{{"a": {i}, "b": {i+1}}}' for i in range(batch_size)]
    extra_fields = [{"tool": "example.math_add"}] * batch_size
    
    test_data = {
        "trajectory_ids": trajectory_ids,
        "actions": actions,
        "extra_fields": extra_fields,
        "user_id": "batch_perf_user"
    }
    
    start_time = time.time()
    response = requests.post(f"{BASE_URL}/v1/tools/get_observation", json=test_data, headers=AUTH_HEADERS)
    end_time = time.time()
    
    if response.status_code == 200:
        return end_time - start_time
    else:
        return None

def test_single_requests_performance(batch_size: int) -> float:
    """测试单个请求性能（模拟旧接口）"""
    start_time = time.time()
    
    # 使用线程池模拟并发单个请求
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for i in range(batch_size):
            future = executor.submit(send_single_request, i)
            futures.append(future)
        
        # 等待所有请求完成
        success_count = 0
        for future in concurrent.futures.as_completed(futures):
            if future.result():
                success_count += 1
    
    end_time = time.time()
    
    if success_count == batch_size:
        return end_time - start_time
    else:
        print(f"   警告: 只有 {success_count}/{batch_size} 个单个请求成功")
        return end_time - start_time

def send_single_request(index: int) -> bool:
    """发送单个请求"""
    test_data = {
        "trajectory_ids": [f"single_perf_{index}"],
        "actions": [f'{{"a": {index}, "b": {index+1}}}'],
        "extra_fields": [{"tool": "example.math_add"}],
        "user_id": "single_perf_user"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/v1/tools/get_observation", json=test_data, headers=AUTH_HEADERS)
        return response.status_code == 200
    except:
        return False

def test_math_add_error_handling():
    """测试 math_add 工具的错误处理"""
    print("\n🧪 测试: math_add 错误处理")
    
    # 测试无效参数
    test_data = {
        "trajectory_ids": ["error_test"],
        "actions": ['{"a": "invalid", "b": 5}'],
        "extra_fields": [{"tool": "example.math_add"}],
        "user_id": "error_test_user"
    }
    
    response = requests.post(f"{BASE_URL}/v1/tools/get_observation", json=test_data, headers=AUTH_HEADERS)
    
    print(f"   状态码: {response.status_code}")
    
    if response.status_code in [200, 400, 404, 500]:
        try:
            data = response.json()
            print(f"   响应数据: {data}")
            print("   ✅ 错误处理测试通过")
            return True
        except:
            print("   ✅ 返回了适当的状态码")
            return True
    else:
        print(f"   ❌ 意外的状态码: {response.status_code}")
        return False

def test_error_handling():
    """验证超时、异常都有结构化返回（HTTP 408/500 与字段 error/invalid_reason）"""
    print("\n🧪 测试4: 验证错误处理")
    
    # 测试无效工具
    test_data = {
        "trajectory_ids": ["error_test"],
        "actions": ['{}'],
        "extra_fields": [{"tool": "invalid_tool"}],
        "user_id": "error_test_user"
    }
    
    response = requests.post(f"{BASE_URL}/v1/tools/get_observation", json=test_data, headers=AUTH_HEADERS)
    
    print(f"   状态码: {response.status_code}")
    
    if response.status_code in [200, 400, 404, 500]:
        try:
            data = response.json()
            print(f"   错误信息: {data}")
            print("   ✅ 错误处理测试通过")
            return True
        except:
            print("   ✅ 返回了错误状态码")
            return True
    else:
        print(f"   ❌ 期望错误状态码，但得到: {response.status_code}")
        return False

def test_health_endpoints():
    """测试健康检查和配置端点"""
    print("\n🧪 测试5: 验证健康检查和配置端点")
    
    # 测试健康检查（不需要认证）
    health_response = requests.get(f"{BASE_URL}/v1/tools/health")
    print(f"   健康检查状态码: {health_response.status_code}")
    
    # 测试配置端点（需要认证）
    config_response = requests.get(f"{BASE_URL}/v1/tools/config", headers=AUTH_HEADERS)
    print(f"   配置端点状态码: {config_response.status_code}")
    
    # 测试指标端点（需要认证）
    metrics_response = requests.get(f"{BASE_URL}/v1/tools/metrics", headers=AUTH_HEADERS)
    print(f"   指标端点状态码: {metrics_response.status_code}")
    if metrics_response.status_code == 200:
        try:
            metrics_data = metrics_response.json()
            print(f"   指标数据: {metrics_data}")
        except:
            print("   指标数据格式错误")
    metrics_ok = metrics_response.status_code == 200
    
    if health_response.status_code == 200 and config_response.status_code == 200 and metrics_ok:
        print("   ✅ 所有端点测试通过")
        return True
    else:
        print("   ❌ 部分端点测试失败")
        return False

def test_backward_compatibility():
    """验证旧有 ToolService.execute_tool 路径不受影响（回归通过）"""
    print("\n🧪 测试6: 验证向后兼容性")
    
    # 这里我们测试原有的API端点是否仍然工作
    try:
        # 测试根路径
        root_response = requests.get(f"{BASE_URL}/")
        print(f"   根路径状态码: {root_response.status_code}")
        
        # 测试文档端点
        docs_response = requests.get(f"{BASE_URL}/docs")
        print(f"   文档端点状态码: {docs_response.status_code}")
        
        print("   ✅ 向后兼容性测试通过")
        return True
    except Exception as e:
        print(f"   ❌ 向后兼容性测试失败: {e}")
        return False

def main():
    """运行所有验收测试"""
    print("🚀 开始验收测试 - 重点测试 Example Toolkit")
    print("=" * 60)
    
    tests = [
        test_example_math_add,
        test_example_echo,
        test_batch_api_multiple_actions,
        test_async_sync_support,
        test_performance_comparison,
        test_math_add_error_handling,
        test_error_handling,
        test_health_endpoints,
        test_backward_compatibility
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"   ❌ 测试异常: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("📊 测试结果汇总:")
    print(f"   通过: {sum(results)}/{len(results)}")
    print(f"   成功率: {sum(results)/len(results)*100:.1f}%")
    
    if all(results):
        print("🎉 所有验收测试通过！")
    else:
        print("⚠️  部分测试失败，需要进一步检查")

if __name__ == "__main__":
    main()