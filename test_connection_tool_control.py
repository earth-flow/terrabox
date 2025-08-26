#!/usr/bin/env python3
"""
测试Connection和ToolOverride机制的工具访问控制功能
验证用户无法执行被禁用的工具
"""

import requests
import json
import sys
from typing import Dict, Any, Optional

# 配置
BASE_URL = "http://localhost:8000"
API_KEY = "tlk_live_DxSgx1kr9iNBFltwGLrEcvov_dT-ZcfBfVRflzn8O8w"  # testuser1's API key

def make_request(method: str, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """发送HTTP请求的通用函数"""
    url = f"{BASE_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    print(f"发送请求: {method} {url}")
    print(f"请求头: {headers}")
    if data:
        print(f"请求数据: {data}")
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data)
        elif method == "PATCH":
            response = requests.patch(url, headers=headers, json=data)
        elif method == "PUT":
            response = requests.put(url, headers=headers, json=data)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers)
        else:
            return {"success": False, "data": {"detail": f"Unsupported method: {method}"}}
        
        print(f"响应状态码: {response.status_code}")
        
        # 尝试解析JSON响应
        try:
            response_data = response.json()
            print(f"响应数据: {response_data}")
        except ValueError:
            response_data = {"detail": "Invalid JSON response"}
            print("响应不是有效的JSON")
        
        return {
            "success": response.status_code < 400,
            "status_code": response.status_code,
            "data": response_data
        }
        
    except requests.exceptions.RequestException as e:
        print(f"请求异常: {str(e)}")
        return {
            "success": False,
            "data": {"detail": f"Request failed: {str(e)}"}
        }

def main():
    """主测试函数"""
    print("开始测试Connection和ToolOverride机制的工具访问控制功能")
    print(f"使用API Key: {API_KEY}")
    print(f"测试服务器: {BASE_URL}")
    
    # 0. 先获取可用的工具包列表
    print("\n=== 获取可用工具包列表 ===")
    toolkits_result = make_request("GET", "/v1/sdk/toolkits")
    
    if not toolkits_result["success"]:
        print(f"❌ 获取工具包列表失败: {toolkits_result.get('data', {}).get('detail', 'Unknown error')}")
        return
    
    toolkits = toolkits_result["data"]
    print(f"✅ 获取工具包列表成功，共 {len(toolkits)} 个工具包")
    for toolkit in toolkits:
        print(f"  - 工具包: {toolkit.get('key', toolkit.get('name', 'Unknown'))}")
    
    # 选择第一个工具包进行测试
    if not toolkits:
        print("❌ 没有可用的工具包，测试终止")
        return
    
    test_toolkit = toolkits[0]
    toolkit_key = test_toolkit.get('key', test_toolkit.get('name', 'unknown'))
    print(f"\n选择工具包进行测试: {toolkit_key}")
    
    # 1. 获取工具包的连接列表
    print(f"\n=== 测试获取{toolkit_key}工具包连接列表 ===")
    connections_result = make_request("GET", f"/v1/sdk/toolkits/{toolkit_key}/connections")
    
    if connections_result["success"]:
        connections = connections_result["data"]
        print(f"✅ 获取{toolkit_key}工具包连接列表成功: {len(connections)} 个连接")
        for conn in connections:
            print(f"  - 连接ID: {conn.get('id')}, 名称: {conn.get('name')}, 状态: {conn.get('status')}")
    else:
        print(f"❌ 获取{toolkit_key}工具包连接列表失败: {connections_result.get('data', {}).get('detail', 'Unknown error')}")
        connections = []
        
    # 如果没有连接，尝试创建一个连接
    if not connections:
        print(f"\n=== 尝试创建{toolkit_key}工具包连接 ===")
        create_result = make_request("POST", f"/v1/sdk/toolkits/{toolkit_key}/connections", {
            "name": f"Test {toolkit_key} Connection",
            "description": f"测试用的{toolkit_key}连接",
            "auth_method": "none"
        })
        
        if create_result["success"]:
            connections = [create_result["data"]]
            print(f"✅ 创建{toolkit_key}连接成功: {connections[0]['id']}")
        else:
            print(f"❌ 创建{toolkit_key}连接失败: {create_result.get('data', {}).get('detail', 'Unknown error')}")
            print("\n❌ 无法创建连接，测试终止")
            return
    
    if not connections:
        print("\n❌ 无法获取连接，测试终止")
        return
    
    # 选择第一个有效连接进行测试
    test_connection = None
    for conn in connections:
        if conn["status"] == "valid":
            test_connection = conn
            break
    
    if not test_connection:
        print("\n❌ 没有找到有效的连接，测试终止")
        return
    
    connection_id = test_connection["id"]
    print(f"\n使用连接进行测试: {test_connection['name']} (ID: {connection_id})")
    
    # 2. 测试设置限制前的工具状态
    test_get_tools_before_restriction()
    test_execute_tool_before_restriction()
    
    # 3. 设置工具覆盖（禁用 example.math_add）
    tool_key = "example.math_add"
    if test_set_tool_override(connection_id, tool_key, False):
        # 4. 测试获取有效工具列表
        test_get_effective_tools(connection_id)
        
        # 5. 测试设置限制后执行工具
        test_execute_tool_after_restriction()
        
        # 6. 恢复工具
        test_remove_tool_override(connection_id, tool_key)
        
        # 7. 再次测试工具执行（应该恢复正常）
        print("\n=== 测试恢复后执行 example.math_add 工具 ===")
        result = make_request("POST", "/v1/sdk/tools/example.math_add/execute", {
            "inputs": {"a": 10, "b": 5}
        })
        
        if result["success"]:
            print(f"✅ 工具执行恢复正常: {result['data']}")
        else:
            print(f"❌ 工具执行仍然失败: {result.get('data', {}).get('detail', 'Unknown error')}")
    
    print("\n=== 连接和工具控制测试完成 ===")


def test_get_tools_before_restriction():
    """测试设置限制前的工具状态"""
    print("\n=== 测试设置限制前的工具状态 ===")
    result = make_request("GET", "/v1/sdk/tools")
    
    if result["success"]:
        tools = result["data"]
        print(f"✅ 获取工具列表成功，共 {len(tools)} 个工具")
        for tool in tools:
            if tool.get('key') == 'example.math_add':
                print(f"  - 找到目标工具: {tool['key']}")
                break
    else:
        print(f"❌ 获取工具列表失败: {result.get('data', {}).get('detail', 'Unknown error')}")


def test_execute_tool_before_restriction():
    """测试设置限制前执行工具"""
    print("\n=== 测试设置限制前执行 example.math_add 工具 ===")
    result = make_request("POST", "/v1/sdk/tools/example.math_add/execute", {
        "inputs": {"a": 10, "b": 5}
    })
    
    if result["success"]:
        print(f"✅ 工具执行成功: {result['data']}")
    else:
        print(f"❌ 工具执行失败: {result.get('data', {}).get('detail', 'Unknown error')}")


def test_set_tool_override(connection_id: str, tool_key: str, enabled: bool) -> bool:
    """设置工具覆盖"""
    action = "禁用" if not enabled else "启用"
    print(f"\n=== 测试{action}工具 {tool_key} ===")
    
    result = make_request("PATCH", f"/v1/sdk/connections/{connection_id}/tools/{tool_key}", {
        "enabled": enabled
    })
    
    if result["success"]:
        print(f"✅ {action}工具成功: {result['data']}")
        return True
    else:
        print(f"❌ {action}工具失败: {result.get('data', {}).get('detail', 'Unknown error')}")
        return False


def test_get_effective_tools(connection_id: str):
    """测试获取有效工具列表"""
    print(f"\n=== 测试获取连接 {connection_id} 的有效工具列表 ===")
    result = make_request("GET", f"/v1/sdk/connections/{connection_id}/tools")
    
    if result["success"]:
        tools_data = result["data"]
        tools = tools_data.get('tools', []) if isinstance(tools_data, dict) else tools_data
        print(f"✅ 获取有效工具列表成功，共 {len(tools)} 个工具")
        
        # 检查 example.math_add 是否在列表中
        math_add_found = False
        for tool in tools:
            tool_key = tool.get('key') or tool.get('slug')
            if tool_key == 'example.math_add':
                math_add_found = True
                print(f"  - 找到 example.math_add 工具: {tool}")
                break
        
        if not math_add_found:
            print("  - example.math_add 工具已被过滤（符合预期）")
    else:
        print(f"❌ 获取有效工具列表失败: {result.get('data', {}).get('detail', 'Unknown error')}")


def test_execute_tool_after_restriction():
    """测试设置限制后执行工具"""
    print("\n=== 测试设置限制后执行 example.math_add 工具 ===")
    result = make_request("POST", "/v1/sdk/tools/example.math_add/execute", {
        "inputs": {"a": 10, "b": 5}
    })
    
    if result["success"]:
        print(f"⚠️ 工具执行成功（可能不符合预期）: {result['data']}")
    else:
        print(f"✅ 工具执行被阻止（符合预期）: {result.get('data', {}).get('detail', 'Unknown error')}")


def test_remove_tool_override(connection_id: str, tool_key: str):
    """恢复工具（通过设置enabled=true）"""
    print(f"\n=== 测试恢复工具 {tool_key} ===")
    result = make_request("PATCH", f"/v1/sdk/connections/{connection_id}/tools/{tool_key}", {
        "enabled": True
    })
    
    if result["success"]:
        print(f"✅ 恢复工具成功: {result['data']}")
    else:
        print(f"❌ 恢复工具失败: {result.get('data', {}).get('detail', 'Unknown error')}")

if __name__ == "__main__":
    main()