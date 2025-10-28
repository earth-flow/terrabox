#!/usr/bin/env python3
"""
Fixed test script for stac_basic tools with correct API format
"""
import requests
import json
import sys

# 服务器配置
BASE_URL = "http://127.0.0.1:8000"
API_KEY = "tlk_live_jHZt0Rw5tt6My8VkCnn95zGKttm9RITOAv74rFfrOpY"
AUTH_HEADERS = {"X-API-Key": API_KEY}

def test_stac_search_fixed():
    """测试stac_basic.search调用，使用正确的API格式"""
    print("=== Testing stac_basic.search with correct API format ===")
    
    # 定义具体的bbox坐标 (欧洲某个区域)
    minx, miny, maxx, maxy = 2.0, 46.0, 3.0, 47.0
    
    # 正确的API请求格式
    test_data = {
        "trajectory_ids": ["test_trajectory_1"],
        "actions": [
            json.dumps({
                "endpoint": "https://earth-search.aws.element84.com/v1",
                "collections": ["sentinel-2-l2a"],
                "datetime": "2024-06-01/2024-06-30",
                "bbox": [minx, miny, maxx, maxy],
                "query": {"eo:cloud_cover": {"lt": 20}},
                "asset_keys": ["B04", "B08"],
                "limit": 50,
                "max_items": 50
            })
        ],
        "extra_fields": [{"tool": "stac_basic.search"}]
    }
    
    try:
        print(f"Sending request to: {BASE_URL}/v1/tools/get_observation")
        print(f"Request data: {json.dumps(test_data, indent=2)}")
        
        response = requests.post(
            f"{BASE_URL}/v1/tools/get_observation",
            json=test_data,
            headers=AUTH_HEADERS,
            timeout=60
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Success! Response keys: {list(result.keys())}")
            
            # 检查返回的数据结构
            if 'observations' in result:
                observations = result['observations']
                if isinstance(observations, list) and len(observations) > 0:
                    first_obs = observations[0]
                    print(f"First observation type: {type(first_obs)}")
                    
                    if isinstance(first_obs, dict):
                        if 'error' in first_obs:
                            print(f"Tool execution error: {first_obs['error']}")
                        elif 'items_minimal' in first_obs:
                            items = first_obs['items_minimal']
                            print(f"Found {len(items)} STAC items")
                            if items:
                                first_item = items[0]
                                print(f"First item ID: {first_item.get('id', 'N/A')}")
                                print(f"First item collection: {first_item.get('collection', 'N/A')}")
                                print(f"First item datetime: {first_item.get('datetime', 'N/A')}")
                        else:
                            print(f"Observation data: {json.dumps(first_obs, indent=2)}")
                    else:
                        print(f"Observation content: {first_obs}")
                else:
                    print("No observations in response")
            else:
                print("No 'observations' field in response")
                print(f"Full response: {json.dumps(result, indent=2)}")
                
        else:
            print(f"Error: {response.status_code}")
            print(f"Response text: {response.text}")
            
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error: {e}")
        print("Make sure the server is running on port 8000")
    except Exception as e:
        print(f"Unexpected error: {e}")

def test_stac_search_california():
    """测试加州地区的stac_basic.search调用"""
    print("\n=== Testing stac_basic.search for California region ===")
    
    # 使用美国加州的bbox坐标
    minx, miny, maxx, maxy = -122.0, 37.0, -121.0, 38.0
    
    test_data = {
        "trajectory_ids": ["test_trajectory_california"],
        "actions": [
            json.dumps({
                "endpoint": "https://earth-search.aws.element84.com/v1",
                "collections": ["sentinel-2-l2a"],
                "datetime": "2024-06-01/2024-06-30",
                "bbox": [minx, miny, maxx, maxy],
                "query": {"eo:cloud_cover": {"lt": 20}},
                "asset_keys": ["B04", "B08"],
                "limit": 10,
                "max_items": 10
            })
        ],
        "extra_fields": [{"tool": "stac_basic.search"}]
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/v1/tools/get_observation",
            json=test_data,
            headers=AUTH_HEADERS,
            timeout=60
        )
        
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if 'observations' in result and isinstance(result['observations'], list):
                obs = result['observations'][0]
                if isinstance(obs, dict) and 'items_minimal' in obs:
                    items = obs['items_minimal']
                    print(f"Found {len(items)} STAC items for California region")
                elif isinstance(obs, dict) and 'error' in obs:
                    print(f"Error for California region: {obs['error']}")
                else:
                    print(f"California result: {obs}")
            else:
                print("No valid observations for California region")
        else:
            print(f"Error: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"Error testing California region: {e}")

def test_stac_stack():
    """测试stac_basic.stack调用"""
    print("\n=== Testing stac_basic.stack ===")
    
    # 首先获取一些STAC items
    search_data = {
        "trajectory_ids": ["test_search_for_stack"],
        "actions": [
            json.dumps({
                "endpoint": "https://earth-search.aws.element84.com/v1",
                "collections": ["sentinel-2-l2a"],
                "datetime": "2024-06-01/2024-06-30",
                "bbox": [2.0, 46.0, 3.0, 47.0],
                "query": {"eo:cloud_cover": {"lt": 20}},
                "asset_keys": ["B04", "B08"],
                "limit": 5,
                "max_items": 5
            })
        ],
        "extra_fields": [{"tool": "stac_basic.search"}]
    }
    
    try:
        # 先搜索获取items
        search_response = requests.post(
            f"{BASE_URL}/v1/tools/get_observation",
            json=search_data,
            headers=AUTH_HEADERS,
            timeout=60
        )
        
        if search_response.status_code == 200:
            search_result = search_response.json()
            if 'observations' in search_result and search_result['observations']:
                search_obs = search_result['observations'][0]
                if isinstance(search_obs, dict) and 'items_minimal' in search_obs:
                    items = search_obs['items_minimal']
                    print(f"Got {len(items)} items for stacking")
                    
                    # 现在测试stack
                    stack_data = {
                        "trajectory_ids": ["test_stack"],
                        "actions": [
                            json.dumps({
                                "items": items,
                                "assets": ["B04", "B08"],
                                "resolution": 10,
                                "crs": "EPSG:4326"
                            })
                        ],
                        "extra_fields": [{"tool": "stac_basic.stack"}]
                    }
                    
                    stack_response = requests.post(
                        f"{BASE_URL}/v1/tools/get_observation",
                        json=stack_data,
                        headers=AUTH_HEADERS,
                        timeout=120
                    )
                    
                    print(f"Stack response status: {stack_response.status_code}")
                    if stack_response.status_code == 200:
                        stack_result = stack_response.json()
                        if 'observations' in stack_result and stack_result['observations']:
                            stack_obs = stack_result['observations'][0]
                            print(f"Stack result type: {type(stack_obs)}")
                            if isinstance(stack_obs, dict):
                                if 'error' in stack_obs:
                                    print(f"Stack error: {stack_obs['error']}")
                                else:
                                    print(f"Stack success! Keys: {list(stack_obs.keys())}")
                            else:
                                print(f"Stack result: {stack_obs}")
                    else:
                        print(f"Stack error: {stack_response.status_code} - {stack_response.text}")
                else:
                    print(f"Search failed: {search_obs}")
            else:
                print("Search returned no valid observations")
        else:
            print(f"Search failed: {search_response.status_code} - {search_response.text}")
            
    except Exception as e:
        print(f"Error testing stack: {e}")

if __name__ == "__main__":
    print("Starting fixed STAC tests...")
    print(f"Target server: {BASE_URL}")
    print(f"Using API key: {API_KEY[:20]}...")
    
    # 测试修复后的search
    test_stac_search_fixed()
    
    # 测试不同地理区域
    test_stac_search_california()
    
    # 测试stack功能
    test_stac_stack()
    
    print("\nFixed STAC tests completed!")