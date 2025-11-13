#!/usr/bin/env python3
import sys
import types
import importlib.util
import asyncio
import json

# Add terrakit src to path
sys.path.insert(0, '/mntssd1/mnt1/xshadow/xdata/git_terra/earthflow/terrakit/src')

# Stub terrakit.core.tool_registry to avoid heavy deps
tool_registry_stub = types.ModuleType('terrakit.core.tool_registry')
class ToolSpec:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
tool_registry_stub.ToolSpec = ToolSpec
sys.modules['terrakit'] = types.ModuleType('terrakit')
sys.modules['terrakit.core'] = types.ModuleType('terrakit.core')
sys.modules['terrakit.core.tool_registry'] = tool_registry_stub

# Stub aiohttp to deterministic behavior
class _MockResponse:
    def __init__(self, status=200):
        self.status = status
        self.headers = {}
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    async def json(self):
        return {
            "language": "python",
            "version": "3.9",
            "run": {
                "stdout": "Hello\n",
                "stderr": "",
                "code": 0,
                "signal": None,
                "cpu_time": 10,
                "memory": 1000000
            }
        }
    async def text(self):
        return "OK"

class _MockClientSession:
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    def get(self, url):
        return _MockResponse(200)
    def post(self, url, json=None):
        return _MockResponse(200)

aiohttp_stub = types.ModuleType('aiohttp')
aiohttp_stub.ClientSession = _MockClientSession
aiohttp_stub.ClientConnectorError = RuntimeError
sys.modules['aiohttp'] = aiohttp_stub

# Import piston module
spec = importlib.util.spec_from_file_location(
    'terrakit.toolkits.piston',
    '/mntssd1/mnt1/xshadow/xdata/git_terra/earthflow/terrakit/src/terrakit/toolkits/piston.py'
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

async def main():
    action_obj = {"language": "python", "files": [{"name": "main.py", "content": "print('ok')"}]}
    action_json = json.dumps(action_obj)
    result = await module.piston_execute_handler({"action": action_json}, {})
    print("valid:", result.get("valid"))
    print("has_result:", "result" in result or "error" in result)

if __name__ == '__main__':
    asyncio.run(main())