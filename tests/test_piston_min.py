import asyncio
import json
import sys
import types


class _MockResponse:
    def __init__(self, status=200):
        self.status = status
        self.headers = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

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
                "memory": 1000000,
            },
        }

    async def text(self):
        return "OK"


class _MockClientSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    def get(self, url):
        return _MockResponse(200)

    def post(self, url, json=None):
        return _MockResponse(200)


def test_piston_execute_minimal():
    aiohttp_stub = types.ModuleType("aiohttp")
    aiohttp_stub.ClientSession = _MockClientSession
    aiohttp_stub.ClientConnectorError = RuntimeError
    sys.modules["aiohttp"] = aiohttp_stub

    from terrabox.toolkits import piston as module

    action_obj = {"language": "python", "files": [{"name": "main.py", "content": "print('ok')"}]}
    action_json = json.dumps(action_obj)
    result = asyncio.run(module.piston_execute_handler({"action": action_json}, {}))

    assert result.get("valid") is True
