"""
Unified Registry for toolkits and tools.
Merges functionalities of previous runtime_registry and tool_registry.
"""
from __future__ import annotations
import logging
from typing import Callable, Dict, List, Optional, Any
from threading import RLock
from dataclasses import dataclass
import json
import hashlib
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------------------

class ToolSpec(BaseModel):
    """Tool specification model."""
    model_config = ConfigDict(from_attributes=True)
    
    slug: str
    name: str
    description: str
    parameters: Dict[str, Any]
    requires_connection: bool = False
    required_scopes: Optional[List[str]] = None


class Toolkit(BaseModel):
    """Toolkit model."""
    model_config = ConfigDict(from_attributes=True)
    
    name: str
    description: str
    version: Optional[str] = None


@dataclass
class ToolDefinition:
    """Simplified tool definition for override management and execution."""
    tool_key: str
    name: str
    description: str
    input_schema: Dict[str, Any]
    default_enabled: bool = True
    default_config: Optional[Dict[str, Any]] = None
    required_scopes: Optional[List[str]] = None
    digest: Optional[str] = None
    
    def __post_init__(self):
        """Calculate digest if not provided."""
        if self.digest is None:
            self.digest = self._calculate_digest()
    
    def _calculate_digest(self) -> str:
        """Calculate SHA256 digest of tool definition."""
        content = {
            "tool_key": self.tool_key,
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "default_enabled": self.default_enabled,
            "default_config": self.default_config,
            "required_scopes": self.required_scopes
        }
        content_str = json.dumps(content, sort_keys=True)
        return hashlib.sha256(content_str.encode()).hexdigest()
    
    @classmethod
    def from_tool_spec(cls, tool_spec: ToolSpec) -> 'ToolDefinition':
        """Create ToolDefinition from ToolSpec."""
        return cls(
            tool_key=tool_spec.slug,
            name=tool_spec.name,
            description=tool_spec.description,
            input_schema=tool_spec.parameters,
            default_enabled=True,
            required_scopes=getattr(tool_spec, 'required_scopes', None)
        )

# -----------------------------------------------------------------------------
# Registry
# -----------------------------------------------------------------------------

# Handler type alias
ExecuteHandler = Callable[[dict, dict, object | None], dict]

class CoreRegistry:
    """
    Central registry for all toolkits and tools.
    Thread-safe, singleton-like usage pattern recommended.
    """
    
    def __init__(self):
        self._lock = RLock()
        self._toolkits: Dict[str, Toolkit] = {}           # name -> Toolkit
        self._tools: Dict[str, Dict[str, object]] = {}    # slug -> {"spec": ToolSpec, "handler": ExecuteHandler}

    def register_toolkit(self, name: str, description: str, version: Optional[str] = None) -> None:
        """Register a toolkit."""
        with self._lock:
            self._toolkits[name] = Toolkit(name=name, description=description, version=version)
            logger.debug(f"Registered toolkit: {name}")

    def register_tool(self, spec: ToolSpec, handler: ExecuteHandler) -> None:
        """Register a tool with its handler."""
        with self._lock:
            self._tools[spec.slug] = {"spec": spec, "handler": handler}
            logger.debug(f"Registered tool: {spec.slug}")

    def get_toolkit(self, name: str) -> Optional[Toolkit]:
        """Get a toolkit by name."""
        with self._lock:
            return self._toolkits.get(name)

    def list_toolkits(self) -> List[Toolkit]:
        """List all registered toolkits."""
        with self._lock:
            return list(self._toolkits.values())

    def get_tool(self, slug: str) -> Optional[ToolSpec]:
        """Get a tool specification by slug."""
        with self._lock:
            rec = self._tools.get(slug)
            return rec["spec"] if rec else None
            
    def get_tool_definition(self, slug: str) -> Optional[ToolDefinition]:
        """Get a tool definition (compatible with override service) by slug."""
        spec = self.get_tool(slug)
        if spec:
            return ToolDefinition.from_tool_spec(spec)
        return None

    def get_handler(self, slug: str) -> Optional[ExecuteHandler]:
        """Get a tool's execution handler by slug."""
        with self._lock:
            rec = self._tools.get(slug)
            return rec["handler"] if rec else None

    def list_tools(self, toolkit: Optional[str] = None) -> List[ToolSpec]:
        """
        List tool specifications.
        If toolkit is provided, filters tools belonging to that toolkit (prefix match).
        """
        with self._lock:
            specs = [v["spec"] for v in self._tools.values()]
            if not toolkit:
                return specs
            # Filter by toolkit name using slug prefix (e.g., "github.list_user_repos" belongs to "github" toolkit)
            return [s for s in specs if s.slug.startswith(f"{toolkit}.")]

    def list_tool_definitions(self, toolkit: Optional[str] = None) -> List[ToolDefinition]:
        """List tool definitions (compatible with override service)."""
        specs = self.list_tools(toolkit)
        return [ToolDefinition.from_tool_spec(s) for s in specs]

    def clear(self) -> None:
        """Clear the registry (useful for testing)."""
        with self._lock:
            self._toolkits.clear()
            self._tools.clear()

# Global instance
registry = CoreRegistry()

# -----------------------------------------------------------------------------
# Registrar Helper (for plugins)
# -----------------------------------------------------------------------------

class Registrar:
    """Helper class passed to plugins for registration."""
    
    def __init__(self, registry_instance: CoreRegistry):
        self.registry = registry_instance
        
    def toolkit(self, name: str, description: str, version: Optional[str] = None):
        self.registry.register_toolkit(name, description, version)
        
    def tool(self, spec: ToolSpec, handler: ExecuteHandler):
        self.registry.register_tool(spec, handler)

# Helper functions for backward compatibility or ease of use
def register_toolkit(name: str, description: str, version: Optional[str] = None) -> None:
    registry.register_toolkit(name, description, version)

def register_tool(spec: ToolSpec, handler: ExecuteHandler) -> None:
    registry.register_tool(spec, handler)

def list_toolkits() -> List[Toolkit]:
    return registry.list_toolkits()

def list_tools(toolkit: Optional[str] = None) -> List[ToolSpec]:
    return registry.list_tools(toolkit)

def get_tool(slug: str) -> Optional[ToolSpec]:
    return registry.get_tool(slug)

def get_handler(slug: str) -> Optional[ExecuteHandler]:
    return registry.get_handler(slug)

def get_tool_registry() -> CoreRegistry:
    """Compatibility accessor."""
    return registry
