#!/usr/bin/env python3
"""
OAuth功能测试脚本

这个脚本测试TerraLink平台的OAuth认证功能，包括：
1. 获取OAuth提供商列表
2. 发起OAuth认证
3. 模拟OAuth回调处理
4. OAuth账户管理

使用方法：
    python tests/test_oauth.py
"""

import requests
import json
import sys
from typing import Dict, Any

# 配置
BASE_URL = "http://localhost:8000/v1"
REDIRECT_URI = "http://localhost:3000/auth/callback"

class OAuthTester:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json'
        })
    
    def test_get_providers(self) -> bool:
        """测试获取OAuth提供商列表"""
        print("\n🔍 测试获取OAuth提供商列表...")
        
        try:
            response = self.session.get(f"{self.base_url}/oauth/providers")
            response.raise_for_status()
            
            providers = response.json()
            print(f"✅ 成功获取 {len(providers)} 个OAuth提供商")
            
            for provider in providers:
                print(f"   - {provider['display_name']} ({provider['name']})")
                print(f"     认证URL: {provider['auth_url']}")
                print(f"     作用域: {provider['scopes']}")
                print(f"     状态: {'活跃' if provider['is_active'] else '非活跃'}")
            
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"❌ 获取OAuth提供商失败: {e}")
            return False
    
    def test_initiate_auth(self, provider: str = "google") -> Dict[str, Any]:
        """测试发起OAuth认证"""
        print(f"\n🚀 测试发起{provider.upper()}认证...")
        
        try:
            payload = {
                "provider": provider,
                "redirect_uri": REDIRECT_URI
            }
            
            response = self.session.post(
                f"{self.base_url}/oauth/auth",
                data=json.dumps(payload)
            )
            response.raise_for_status()
            
            auth_data = response.json()
            print(f"✅ 成功生成{provider.upper()}认证URL")
            print(f"   认证URL: {auth_data['auth_url'][:100]}...")
            print(f"   状态码: {auth_data['state']}")
            
            return auth_data
            
        except requests.exceptions.RequestException as e:
            print(f"❌ 发起{provider.upper()}认证失败: {e}")
            return {}
    
    def test_oauth_callback_validation(self) -> bool:
        """测试OAuth回调端点的参数验证"""
        print("\n🔄 测试OAuth回调参数验证...")
        
        try:
            # 测试缺少必需参数
            invalid_payload = {
                "provider": "google"
                # 缺少code和state
            }
            
            response = self.session.post(
                f"{self.base_url}/oauth/callback",
                data=json.dumps(invalid_payload)
            )
            
            if response.status_code == 422:  # Validation error
                print("✅ OAuth回调参数验证正常工作")
                return True
            else:
                print(f"⚠️  OAuth回调参数验证可能有问题，状态码: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 测试OAuth回调验证失败: {e}")
            return False
    
    def test_health_check(self) -> bool:
        """测试服务器健康状态"""
        print("\n💓 检查服务器健康状态...")
        
        try:
            response = self.session.get(f"{self.base_url.replace('/v1', '')}")
            response.raise_for_status()
            
            health_data = response.json()
            if health_data.get('status') == 'ok':
                print("✅ 服务器运行正常")
                return True
            else:
                print(f"⚠️  服务器状态异常: {health_data}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 服务器健康检查失败: {e}")
            return False
    
    def run_all_tests(self) -> bool:
        """运行所有OAuth测试"""
        print("🧪 开始OAuth功能测试")
        print("=" * 50)
        
        tests = [
            self.test_health_check,
            self.test_get_providers,
            lambda: self.test_initiate_auth("google"),
            lambda: self.test_initiate_auth("github"),
            self.test_oauth_callback_validation
        ]
        
        passed = 0
        total = len(tests)
        
        for test in tests:
            try:
                result = test()
                if result:
                    passed += 1
            except Exception as e:
                print(f"❌ 测试执行异常: {e}")
        
        print("\n" + "=" * 50)
        print(f"📊 测试结果: {passed}/{total} 通过")
        
        if passed == total:
            print("🎉 所有OAuth测试通过！")
            return True
        else:
            print("⚠️  部分测试失败，请检查上述错误信息")
            return False

def main():
    """主函数"""
    print("TerraLink Platform OAuth 测试工具")
    print("确保服务器正在运行在 http://localhost:8000")
    
    tester = OAuthTester()
    success = tester.run_all_tests()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()