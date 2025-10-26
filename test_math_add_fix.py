#!/usr/bin/env python3
"""
测试math.add工具的参数传递修复效果
"""

import requests
import json

def test_math_add_fix():
    """测试math.add工具是否能正确接收和处理参数"""
    
    base_url = "http://127.0.0.1:8001"
    
    # 测试数据
    test_cases = [
        {"a": 5, "b": 3, "expected": 8},
        {"a": 10, "b": 20, "expected": 30},
        {"a": -5, "b": 15, "expected": 10},
        {"a": 0.5, "b": 0.3, "expected": 0.8}
    ]
    
    print("🧪 测试math.add工具参数传递修复效果")
    print("=" * 50)
    
    for i, test_case in enumerate(test_cases, 1):
        a, b, expected = test_case["a"], test_case["b"], test_case["expected"]
        
        # 准备请求数据
        payload = {
            "trajectory_ids": [f"test_{i}"],
            "actions": [json.dumps({"a": a, "b": b})],
            "extra_fields": [{"tool": "example.math_add"}],
            "user_id": "test_user"
        }
        
        try:
            # 发送请求
            response = requests.post(f"{base_url}/v1/tools/get_observation", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                observations = data.get("observations", [])
                
                if observations:
                    result = observations[0]
                    
                    if "error" in result:
                        print(f"❌ 测试 {i}: 输入 a={a}, b={b} - 错误: {result['error']}")
                    else:
                        actual_result = result.get("result", 0)
                        operation = result.get("operation", "")
                        
                        print(f"📊 测试 {i}: 输入 a={a}, b={b}")
                        print(f"   期望结果: {expected}")
                        print(f"   实际结果: {actual_result}")
                        print(f"   操作描述: {operation}")
                        
                        if abs(actual_result - expected) < 0.0001:  # 浮点数比较
                            print(f"   ✅ 测试通过")
                        else:
                            print(f"   ❌ 测试失败")
                else:
                    print(f"❌ 测试 {i}: 没有返回观察结果")
            else:
                print(f"❌ 测试 {i}: HTTP错误 {response.status_code}")
                
        except Exception as e:
            print(f"❌ 测试 {i}: 异常 {e}")
        
        print()

if __name__ == "__main__":
    test_math_add_fix()