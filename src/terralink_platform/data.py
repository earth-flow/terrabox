""" 
Runtime registry for toolkits and tools (spec + handler). 
All user/account/connection data lives in the database. 
Thread-safe, tiny, in-memory. 
""" 
from __future__ import annotations 
from typing import Callable, Dict, List, Optional 
from threading import RLock 
from .models import ToolSpec, Toolkit  # Pydantic API schemas 

# handler 形状：handler(arguments: dict, context: dict, connected_account_or_none) -> dict 
ExecuteHandler = Callable[[dict, dict, object | None], dict] 

_LOCK = RLock() 
_TOOLKITS: Dict[str, Toolkit] = {}           # name -> Toolkit 
_TOOLS: Dict[str, Dict[str, object]] = {}    # slug -> {"spec": ToolSpec, "handler": ExecuteHandler} 

def register_toolkit(name: str, description: str) -> None: 
    with _LOCK: 
        _TOOLKITS[name] = Toolkit(name=name, description=description) 

def list_toolkits() -> List[Toolkit]: 
    with _LOCK: 
        return list(_TOOLKITS.values()) 

def register_tool(spec: ToolSpec, handler: ExecuteHandler) -> None: 
    with _LOCK: 
        _TOOLS[spec.slug] = {"spec": spec, "handler": handler} 

def get_tool(slug: str) -> Optional[ToolSpec]: 
    with _LOCK: 
        rec = _TOOLS.get(slug) 
        return rec["spec"] if rec else None 

def get_handler(slug: str) -> Optional[ExecuteHandler]: 
    with _LOCK: 
        rec = _TOOLS.get(slug) 
        return rec["handler"] if rec else None 

def list_tools(toolkit: Optional[str] = None) -> List[ToolSpec]: 
    with _LOCK: 
        specs = [v["spec"] for v in _TOOLS.values()] 
        return [s for s in specs if (not toolkit or s.toolkit == toolkit)] 

# 测试用：清空注册表 
def _reset_registry_for_tests() -> None:     # pragma: no cover 
    with _LOCK: 
        _TOOLKITS.clear() 
        _TOOLS.clear()
