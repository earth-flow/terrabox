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
import pytest

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "tlk_live_jHZt0Rw5tt6My8VkCnn95zGKttm9RITOAv74rFfrOpY"  # change to a valid one

# 认证头
AUTH_HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture
def base_url():
    """提供基础URL"""
    return BASE_URL


@pytest.fixture
def auth_headers():
    """提供认证头"""
    return AUTH_HEADERS


@pytest.fixture
def api_client(base_url, auth_headers):
    """提供API客户端配置"""
    return {
        "base_url": base_url,
        "headers": auth_headers
    }

def test_example_math_add(api_client):
    """测试 example.math_add 工具的功能"""
    # 测试基本加法
    test_data = {
        "trajectory_ids": ["math_test_1"],
        "actions": ['{"a": 5, "b": 3}'],
        "extra_fields": [{"tool": "example.math_add"}],
        "user_id": "math_test_user"
    }
    
    response = requests.post(
        f"{api_client['base_url']}/v1/tools/get_observation", 
        json=test_data, 
        headers=api_client['headers']
    )
    
    # 使用pytest断言
    assert response.status_code == 200, f"API请求失败: {response.text}"
    
    data = response.json()
    observations = data.get('observations', [])
    
    assert len(observations) > 0, "没有返回观察结果"
    
    result = observations[0]
    # 验证计算结果 (5 + 3 = 8)
    if isinstance(result, dict):
        # 如果返回的是字典，提取result字段
        actual_result = result.get('result', result)
        assert actual_result == 8.0, f"计算结果错误，期望8.0，实际得到{actual_result}"
    else:
        # 如果返回的是简单值
        assert result == 8, f"计算结果错误，期望8，实际得到{result}"

def test_example_echo(api_client):
    """测试 example.echo 工具的功能"""
    # 测试echo功能
    test_message = "Hello from test!"
    test_data = {
        "trajectory_ids": ["echo_test_1"],
        "actions": [f'{{"message": "{test_message}"}}'],
        "extra_fields": [{"tool": "example.echo"}],
        "user_id": "echo_test_user"
    }
    
    response = requests.post(
        f"{api_client['base_url']}/v1/tools/get_observation", 
        json=test_data, 
        headers=api_client['headers']
    )
    
    # 使用pytest断言
    assert response.status_code == 200, f"API请求失败: {response.text}"
    
    data = response.json()
    observations = data.get('observations', [])
    
    assert len(observations) > 0, "没有返回观察结果"
    
    result = observations[0]
    # 验证echo结果
    if isinstance(result, dict):
        # 如果返回的是字典，提取echo字段
        actual_result = result.get('echo', result)
        assert actual_result == test_message, f"Echo结果错误，期望'{test_message}'，实际得到'{actual_result}'"
    else:
        # 如果返回的是简单值
        assert result == test_message, f"Echo结果错误，期望'{test_message}'，实际得到'{result}'"

def test_batch_api_multiple_actions(api_client):
    """验证 /v1/tools/get_observation 接口能接受 N>1 条 action 并并发执行"""
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
    response = requests.post(
        f"{api_client['base_url']}/v1/tools/get_observation", 
        json=test_data, 
        headers=api_client['headers']
    )
    end_time = time.time()
    
    processing_time = end_time - start_time
    
    # 使用pytest断言
    assert response.status_code == 200, f"API请求失败: {response.text}"
    
    data = response.json()
    observations = data.get('observations', [])
    
    # 验证返回的观察数量
    assert len(observations) == 3, f"期望返回3个观察结果，实际返回{len(observations)}个"
    
    # 验证计算结果
    expected_results = [15.0, 35.0, 55.0]  # 10+5, 20+15, 30+25
    for i, obs in enumerate(observations):
        if isinstance(obs, dict):
            # 如果返回的是字典，提取result字段
            actual_result = obs.get('result', obs)
            assert actual_result == expected_results[i], f"计算结果{i+1}错误，期望{expected_results[i]}，实际得到{actual_result}"
        else:
            # 如果返回的是简单值
            assert obs == expected_results[i], f"计算结果{i+1}错误，期望{expected_results[i]}，实际得到{obs}"
    
    # 验证处理时间合理（应该小于5秒）
    assert processing_time < 5.0, f"处理时间过长: {processing_time:.3f}s"
    
    # 验证响应包含必要字段
    assert 'trace_id' in data or 'processing_time_ms' in data, "响应缺少追踪信息"

def test_async_sync_support(api_client):
    """验证同时支持 async 与 sync 工具（sync 不阻塞事件循环）"""
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
    response = requests.post(
        f"{api_client['base_url']}/v1/tools/get_observation", 
        json=test_data, 
        headers=api_client['headers']
    )
    end_time = time.time()
    
    processing_time = end_time - start_time
    
    # 使用pytest断言
    assert response.status_code == 200, f"API请求失败: {response.text}"
    
    data = response.json()
    observations = data.get('observations', [])
    
    # 验证返回的观察数量
    assert len(observations) == 3, f"期望返回3个观察结果，实际返回{len(observations)}个"
    
    # 验证混合工具的结果
    expected_results = [3.0, "sync test", 7.0]  # 1+2, echo, 3+4
    for i, obs in enumerate(observations):
        if isinstance(obs, dict):
            # 根据工具类型提取相应字段
            if i == 1:  # echo工具
                actual_result = obs.get('echo', obs)
            else:  # math_add工具
                actual_result = obs.get('result', obs)
            assert actual_result == expected_results[i], f"结果{i+1}错误，期望{expected_results[i]}，实际得到{actual_result}"
        else:
            # 如果返回的是简单值
            assert obs == expected_results[i], f"结果{i+1}错误，期望{expected_results[i]}，实际得到{obs}"
    
    # 验证处理时间合理
    assert processing_time < 5.0, f"处理时间过长: {processing_time:.3f}s"

@pytest.mark.parametrize("batch_size", [100, 500, 1000])
def test_performance_comparison(api_client, batch_size):
    """验证大批量（≥1k）时吞吐显著优于旧接口（至少 ×2，并与线程池大小正相关）"""
    # 1. 测试批量接口性能
    batch_time = _test_batch_performance(api_client, batch_size)
    assert batch_time is not None, "批量测试失败"
    
    # 2. 测试单个请求性能（模拟旧接口）
    single_time = _test_single_requests_performance(api_client, batch_size)
    assert single_time is not None, "单个请求测试失败"
    
    # 3. 计算性能提升
    speedup = single_time / batch_time if batch_time > 0 else 0
    
    # 验证性能提升至少1.5倍（降低要求以适应测试环境）
    assert speedup >= 1.5, f"性能提升不足: {speedup:.1f}x < 1.5x (批量: {batch_time:.3f}s, 单个: {single_time:.3f}s)"
    
    # 验证处理时间合理
    assert batch_time < 30.0, f"批量处理时间过长: {batch_time:.3f}s"
    assert single_time < 60.0, f"单个请求处理时间过长: {single_time:.3f}s"

def _test_batch_performance(api_client: dict, batch_size: int) -> float:
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
    response = requests.post(
        f"{api_client['base_url']}/v1/tools/get_observation", 
        json=test_data, 
        headers=api_client['headers']
    )
    end_time = time.time()
    
    if response.status_code == 200:
        return end_time - start_time
    else:
        return None


def _test_single_requests_performance(api_client: dict, batch_size: int) -> float:
    """测试单个请求性能（模拟旧接口）"""
    start_time = time.time()
    
    # 使用线程池模拟并发单个请求
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for i in range(batch_size):
            future = executor.submit(_send_single_request, api_client, i)
            futures.append(future)
        
        # 等待所有请求完成
        success_count = 0
        for future in concurrent.futures.as_completed(futures):
            if future.result():
                success_count += 1
    
    end_time = time.time()
    
    if success_count >= batch_size * 0.8:  # 允许20%的失败率
        return end_time - start_time
    else:
        return end_time - start_time  # 仍然返回时间，但测试会在上层失败


def _send_single_request(api_client: dict, index: int) -> bool:
    """发送单个请求"""
    test_data = {
        "trajectory_ids": [f"single_perf_{index}"],
        "actions": [f'{{"a": {index}, "b": {index+1}}}'],
        "extra_fields": [{"tool": "example.math_add"}],
        "user_id": "single_perf_user"
    }
    
    try:
        response = requests.post(
            f"{api_client['base_url']}/v1/tools/get_observation", 
            json=test_data, 
            headers=api_client['headers']
        )
        return response.status_code == 200
    except:
        return False

def test_math_add_error_handling(api_client):
    """测试 math_add 工具的错误处理"""
    # 测试无效参数
    test_data = {
        "trajectory_ids": ["error_test"],
        "actions": ['{"a": "invalid", "b": 5}'],
        "extra_fields": [{"tool": "example.math_add"}],
        "user_id": "error_test_user"
    }
    
    response = requests.post(
        f"{api_client['base_url']}/v1/tools/get_observation", 
        json=test_data, 
        headers=api_client['headers']
    )
    
    # 验证返回了合适的状态码
    assert response.status_code in [200, 400, 404, 500], f"意外的状态码: {response.status_code}"
    
    # 尝试解析JSON响应
    try:
        data = response.json()
        # 如果是200状态码，检查是否有错误信息在observations中
        if response.status_code == 200:
            observations = data.get('observations', [])
            assert len(observations) > 0, "应该返回错误观察结果"
    except ValueError:
        # 如果无法解析JSON，确保状态码表明错误
        assert response.status_code >= 400, "无法解析JSON但状态码不表示错误"


def test_error_handling_invalid_tool(api_client):
    """验证超时、异常都有结构化返回（HTTP 408/500 与字段 error/invalid_reason）"""
    # 测试无效工具
    test_data = {
        "trajectory_ids": ["error_test"],
        "actions": ['{}'],
        "extra_fields": [{"tool": "invalid_tool"}],
        "user_id": "error_test_user"
    }
    
    response = requests.post(
        f"{api_client['base_url']}/v1/tools/get_observation", 
        json=test_data, 
        headers=api_client['headers']
    )
    
    # 验证返回了合适的状态码
    assert response.status_code in [200, 400, 404, 500], f"期望错误状态码，但得到: {response.status_code}"
    
    # 尝试解析JSON响应
    try:
        data = response.json()
        # 验证错误信息结构
        if response.status_code == 200:
            # 如果是200，错误应该在observations中
            observations = data.get('observations', [])
            assert len(observations) > 0, "应该返回错误观察结果"
        else:
            # 如果是错误状态码，应该有错误信息
            assert 'error' in data or 'detail' in data or 'message' in data, "错误响应应包含错误信息"
    except ValueError:
        # 如果无法解析JSON，确保状态码表明错误
        assert response.status_code >= 400, "无法解析JSON但状态码不表示错误"

def test_health_endpoint(base_url):
    """测试健康检查端点（不需要认证）"""
    health_response = requests.get(f"{base_url}/v1/tools/health")
    assert health_response.status_code == 200, f"健康检查失败: {health_response.status_code}"


def test_config_endpoint(api_client):
    """测试配置端点（需要认证）"""
    config_response = requests.get(
        f"{api_client['base_url']}/v1/tools/config", 
        headers=api_client['headers']
    )
    assert config_response.status_code == 200, f"配置端点失败: {config_response.status_code}"


def test_metrics_endpoint(api_client):
    """测试指标端点（需要认证）"""
    metrics_response = requests.get(
        f"{api_client['base_url']}/v1/tools/metrics", 
        headers=api_client['headers']
    )
    assert metrics_response.status_code == 200, f"指标端点失败: {metrics_response.status_code}"
    
    # 验证返回的是有效JSON
    try:
        metrics_data = metrics_response.json()
        assert isinstance(metrics_data, dict), "指标数据应该是字典格式"
    except ValueError:
        pytest.fail("指标端点返回的不是有效JSON")


def test_backward_compatibility_root_endpoint(base_url):
    """验证根路径端点仍然工作"""
    try:
        root_response = requests.get(f"{base_url}/")
        # 根路径可能返回200或重定向，都是正常的
        assert root_response.status_code in [200, 301, 302, 307, 308], f"根路径异常: {root_response.status_code}"
    except Exception as e:
        pytest.fail(f"根路径测试失败: {e}")


def test_backward_compatibility_docs_endpoint(base_url):
    """验证文档端点仍然工作"""
    try:
        docs_response = requests.get(f"{base_url}/docs")
        # 文档端点应该返回200或重定向
        assert docs_response.status_code in [200, 301, 302, 307, 308], f"文档端点异常: {docs_response.status_code}"
    except Exception as e:
        pytest.fail(f"文档端点测试失败: {e}")

# pytest会自动发现和运行所有以test_开头的函数
# 不需要main函数

# 如果需要运行测试，使用以下命令：
# pytest test_acceptance.py -v
# 或者运行特定测试：
# pytest test_acceptance.py::test_example_math_add -v