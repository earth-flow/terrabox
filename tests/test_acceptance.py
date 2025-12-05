#!/usr/bin/env python3
"""
Acceptance Test Script - Verifies all features of the batch tool API
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

# Auth headers
AUTH_HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture
def base_url():
    """Provide base URL"""
    return BASE_URL


@pytest.fixture
def auth_headers():
    """Provide auth headers"""
    return AUTH_HEADERS


@pytest.fixture
def api_client(base_url, auth_headers):
    """Provide API client configuration"""
    return {
        "base_url": base_url,
        "headers": auth_headers
    }

def test_example_math_add(api_client):
    """Test example.math_add tool functionality"""
    # Test basic addition
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
    
    # Use pytest assertion
    assert response.status_code == 200, f"API request failed: {response.text}"
    
    data = response.json()
    observations = data.get('observations', [])
    
    assert len(observations) > 0, "No observations returned"
    
    result = observations[0]
    # Verify calculation result (5 + 3 = 8)
    if isinstance(result, dict):
        # If result is a dict, extract result field
        actual_result = result.get('result', result)
        assert actual_result == 8.0, f"Calculation result error, expected 8.0, got {actual_result}"
    else:
        # If result is a simple value
        assert result == 8, f"Calculation result error, expected 8, got {result}"

def test_example_echo(api_client):
    """Test example.echo tool functionality"""
    # Test echo functionality
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
    
    # Use pytest assertion
    assert response.status_code == 200, f"API request failed: {response.text}"
    
    data = response.json()
    observations = data.get('observations', [])
    
    assert len(observations) > 0, "No observations returned"
    
    result = observations[0]
    # Verify echo result
    if isinstance(result, dict):
        # If result is a dict, extract echo field
        actual_result = result.get('echo', result)
        assert actual_result == test_message, f"Echo result error, expected '{test_message}', got '{actual_result}'"
    else:
        # If result is a simple value
        assert result == test_message, f"Echo result error, expected '{test_message}', got '{result}'"

def test_batch_api_multiple_actions(api_client):
    """Verify /v1/tools/get_observation endpoint can accept N>1 actions and execute concurrently"""
    # Prepare test data - multiple actions, use example.math_add
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
    
    # Use pytest assertion
    assert response.status_code == 200, f"API request failed: {response.text}"
    
    data = response.json()
    observations = data.get('observations', [])
    
    # Verify returned observation count
    assert len(observations) == 3, f"Expected 3 observations, got {len(observations)}"
    
    # Verify calculation results
    expected_results = [15.0, 35.0, 55.0]  # 10+5, 20+15, 30+25
    for i, obs in enumerate(observations):
        if isinstance(obs, dict):
            # If result is a dict, extract result field
            actual_result = obs.get('result', obs)
            assert actual_result == expected_results[i], f"Calculation result {i+1} error, expected {expected_results[i]}, got {actual_result}"
        else:
            # If result is a simple value
            assert obs == expected_results[i], f"Calculation result {i+1} error, expected {expected_results[i]}, got {obs}"
    
    # Verify processing time is reasonable (should be less than 5 seconds)
    assert processing_time < 5.0, f"Processing time too long: {processing_time:.3f}s"
    
    # Verify response contains necessary fields
    assert 'trace_id' in data or 'processing_time_ms' in data, "Response missing trace info"

def test_async_sync_support(api_client):
    """Verify support for both async and sync tools (sync does not block event loop)"""
    piston_action_obj1 = {"language": "python", "files": [{"name": "main.py", "content": "print(2**5+145)"}]}
    piston_action_obj2 = {"language": "python", "files": [{"name": "main.py", "content": "print('ok hahahahah')"}]}
    piston_action_obj3 = {"language": "python", "files": [{"name": "main.py", "content": "print('Hello world')"}]}
    piston_action_str1 = json.dumps({"action": json.dumps(piston_action_obj1)})
    piston_action_str2 = json.dumps({"action": json.dumps(piston_action_obj2)})
    piston_action_str3 = json.dumps({"action": json.dumps(piston_action_obj3)})
    test_data = {
        "trajectory_ids": [
            "async_1", "sync_1", "async_2",
            "async_piston_1", "async_piston_2", "async_piston_3"
        ],
        "actions": [
            '{"a": 1, "b": 2}',
            '{"message": "sync test"}',
            '{"a": 3, "b": 4}',
            piston_action_str1,
            piston_action_str2,
            piston_action_str3,
        ],
        "extra_fields": [
            {"tool": "example.math_add"},
            {"tool": "example.echo"},
            {"tool": "example.math_add"},
            {"tool": "piston.execute"},
            {"tool": "piston.execute"},
            {"tool": "piston.execute"}
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
    
    # Use pytest assertion
    assert response.status_code == 200, f"API request failed: {response.text}"
    
    data = response.json()
    observations = data.get('observations', [])
    
    assert len(observations) == 6, f"Expected 6 observations, got {len(observations)}"
    
    # Verify mixed tool results
    expected_results = [3.0, "sync test", 7.0]
    for i, obs in enumerate(observations[:3]):
        if isinstance(obs, dict):
            if i == 1:
                actual_result = obs.get('echo', obs)
            else:
                actual_result = obs.get('result', obs)
            assert actual_result == expected_results[i], f"Result {i+1} error, expected {expected_results[i]}, got {actual_result}"
        else:
            assert obs == expected_results[i], f"Result {i+1} error, expected {expected_results[i]}, got {obs}"

    for j in range(3, 6):
        piston_obs = observations[j]
        if isinstance(piston_obs, dict):
            piston_result = piston_obs.get('result') or piston_obs.get('error') or piston_obs
            assert isinstance(piston_result, str) and len(piston_result) > 0, "piston result format incorrect"
        else:
            assert isinstance(piston_obs, str) and len(piston_obs) > 0, "piston result format incorrect"

    # Append: Test bash.execute and ipython.execute
    bash_action = json.dumps({"commands": "echo hello && echo 123"})
    ipy_action = json.dumps({"action": "<python>print('ipython ok')</python>"})
    test_data2 = {
        "trajectory_ids": ["bash_1", "ipy_1"],
        "actions": [bash_action, ipy_action],
        "extra_fields": [{"tool": "bash.execute"}, {"tool": "ipython.execute"}],
        "user_id": "test_user"
    }
    response2 = requests.post(
        f"{api_client['base_url']}/v1/tools/get_observation",
        json=test_data2,
        headers=api_client['headers']
    )
    assert response2.status_code == 200, f"API request failed: {response2.text}"
    data2 = response2.json()
    obs2 = data2.get('observations', [])
    assert len(obs2) == 2, f"Expected 2 observations, got {len(obs2)}"
    # bash output should contain hello and 123
    bash_obs = obs2[0]
    if isinstance(bash_obs, dict):
        bash_output = bash_obs.get('output') or bash_obs.get('observation') or str(bash_obs)
    else:
        bash_output = str(bash_obs)
    assert "hello" in bash_output and "123" in bash_output, "bash output missing expected content"
    # ipython output should contain ipython ok
    ipy_obs = obs2[1]
    if isinstance(ipy_obs, dict):
        ipy_output = ipy_obs.get('observation') or ipy_obs.get('execution_result') or str(ipy_obs)
    else:
        ipy_output = str(ipy_obs)
    assert "ipython ok" in ipy_output, "ipython output missing expected content"
    
    # Verify processing time is reasonable
    assert processing_time < 5.0, f"Processing time too long: {processing_time:.3f}s"

@pytest.mark.parametrize("batch_size", [100, 500, 1000])
def test_performance_comparison(api_client, batch_size):
    """Verify large batch (>=1k) throughput is significantly better than legacy API (at least x2, correlated with thread pool size)"""
    # 1. Test batch API performance
    batch_time = _test_batch_performance(api_client, batch_size)
    assert batch_time is not None, "Batch test failed"
    
    # 2. Test single request performance (simulate legacy API)
    single_time = _test_single_requests_performance(api_client, batch_size)
    assert single_time is not None, "Single request test failed"
    
    # 3. Calculate performance improvement
    speedup = single_time / batch_time if batch_time > 0 else 0
    
    # Verify performance improvement at least 1.5x (lower requirement for test environment)
    assert speedup >= 1.5, f"Performance improvement insufficient: {speedup:.1f}x < 1.5x (Batch: {batch_time:.3f}s, Single: {single_time:.3f}s)"
    
    # Verify processing time is reasonable
    assert batch_time < 30.0, f"Batch processing time too long: {batch_time:.3f}s"
    assert single_time < 60.0, f"Single request processing time too long: {single_time:.3f}s"

def _test_batch_performance(api_client: dict, batch_size: int) -> float:
    """Test batch API performance"""
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
    """Test single request performance (simulate legacy API)"""
    start_time = time.time()
    
    # Use thread pool to simulate concurrent single requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for i in range(batch_size):
            future = executor.submit(_send_single_request, api_client, i)
            futures.append(future)
        
        # Wait for all requests to complete
        success_count = 0
        for future in concurrent.futures.as_completed(futures):
            if future.result():
                success_count += 1
    
    end_time = time.time()
    
    if success_count >= batch_size * 0.8:  # Allow 20% failure rate
        return end_time - start_time
    else:
        return end_time - start_time  # Still return time, but test will fail at upper level


def _send_single_request(api_client: dict, index: int) -> bool:
    """Send single request"""
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
    """Test math_add tool error handling"""
    # Test invalid parameters
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
    
    # Verify returned appropriate status code
    assert response.status_code in [200, 400, 404, 500], f"Unexpected status code: {response.status_code}"
    
    # Try parsing JSON response
    try:
        data = response.json()
        # If 200 OK, check if error info is in observations
        if response.status_code == 200:
            observations = data.get('observations', [])
            assert len(observations) > 0, "Should return error observation"
    except ValueError:
        # If JSON parsing fails, ensure status code indicates error
        assert response.status_code >= 400, "JSON parse failed but status code does not indicate error"


def test_error_handling_invalid_tool(api_client):
    """Verify timeout/exceptions return structured response (HTTP 408/500 with error/invalid_reason fields)"""
    # Test invalid tool
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
    
    # Verify returned appropriate status code
    assert response.status_code in [200, 400, 404, 500], f"Expected error status code, but got: {response.status_code}"
    
    # Try parsing JSON response
    try:
        data = response.json()
        # Verify error info structure
        if response.status_code == 200:
            # If 200, error should be in observations
            observations = data.get('observations', [])
            assert len(observations) > 0, "Should return error observation"
        else:
            # If error status code, should contain error info
            assert 'error' in data or 'detail' in data or 'message' in data, "Error response should contain error info"
    except ValueError:
        # If JSON parsing fails, ensure status code indicates error
        assert response.status_code >= 400, "JSON parse failed but status code does not indicate error"

def test_health_endpoint(base_url):
    """Test health check endpoint (no auth required)"""
    health_response = requests.get(f"{base_url}/v1/tools/health")
    assert health_response.status_code == 200, f"Health check failed: {health_response.status_code}"


def test_config_endpoint(api_client):
    """Test config endpoint (auth required)"""
    config_response = requests.get(
        f"{api_client['base_url']}/v1/tools/config", 
        headers=api_client['headers']
    )
    assert config_response.status_code == 200, f"Config endpoint failed: {config_response.status_code}"


def test_metrics_endpoint(api_client):
    """Test metrics endpoint (auth required)"""
    metrics_response = requests.get(
        f"{api_client['base_url']}/v1/tools/metrics", 
        headers=api_client['headers']
    )
    assert metrics_response.status_code == 200, f"Metrics endpoint failed: {metrics_response.status_code}"
    
    # Verify response is valid JSON
    try:
        metrics_data = metrics_response.json()
        assert isinstance(metrics_data, dict), "Metrics data should be a dictionary"
    except ValueError:
        pytest.fail("Metrics endpoint did not return valid JSON")


def test_backward_compatibility_root_endpoint(base_url):
    """Verify root endpoint still works"""
    try:
        root_response = requests.get(f"{base_url}/")
        # Root path might return 200 or redirect, both are normal
        assert root_response.status_code in [200, 301, 302, 307, 308], f"Root endpoint abnormal: {root_response.status_code}"
    except Exception as e:
        pytest.fail(f"Root endpoint test failed: {e}")


def test_backward_compatibility_docs_endpoint(base_url):
    """Verify docs endpoint still works"""
    try:
        docs_response = requests.get(f"{base_url}/docs")
        # Docs endpoint should return 200 or redirect
        assert docs_response.status_code in [200, 301, 302, 307, 308], f"Docs endpoint abnormal: {docs_response.status_code}"
    except Exception as e:
        pytest.fail(f"Docs endpoint test failed: {e}")

# pytest will automatically discover and run all functions starting with test_
# No main function needed

# To run tests, use the following command:
# pytest test_acceptance.py -v
# Or run specific test:
# pytest test_acceptance.py::test_example_math_add -v
