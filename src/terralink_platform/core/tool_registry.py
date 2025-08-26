"""Simplified Tool Registry for tool override management."""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import hashlib
import json
from pydantic import BaseModel

# Avoid circular import by importing inside functions when needed


class ToolSpec(BaseModel):
    """Tool specification model."""
    slug: str
    name: str
    description: str
    parameters: Dict[str, Any]
    requires_connection: bool = False
    required_scopes: Optional[List[str]] = None

    class Config:
        from_attributes = True


class Toolkit(BaseModel):
    """Simple toolkit model for data.py compatibility."""
    name: str
    description: str

    class Config:
        from_attributes = True


@dataclass
class ToolDefinition:
    """Simplified tool definition for override management."""
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
            name=tool_spec.slug.split('.')[-1].replace('_', ' ').title(),
            description=tool_spec.description,
            input_schema=tool_spec.parameters,
            default_enabled=True,
            required_scopes=getattr(tool_spec, 'required_scopes', None)
        )


class ToolRegistry:
    """Simplified registry for tool override management."""
    
    def __init__(self):
        pass
    
    def get_tool(self, tool_key: str) -> Optional[ToolDefinition]:
        """Get a tool definition by key from the extensions system."""
        from ..data import get_tool
        tool_spec = get_tool(tool_key)
        if tool_spec:
            return ToolDefinition.from_tool_spec(tool_spec)
        return None
    
    def list_tools(self, app_key: Optional[str] = None) -> List[ToolDefinition]:
        """List all tool definitions from the extensions system."""
        from ..data import list_tools
        tool_specs = list_tools()
        tool_defs = [ToolDefinition.from_tool_spec(spec) for spec in tool_specs]
        
        if app_key:
            # Filter tools by app prefix
            tool_defs = [tool for tool in tool_defs if tool.tool_key.startswith(f"{app_key}.")]
        
        return tool_defs
    



# Global registry instance
_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    return _registry


def initialize_registry() -> None:
    """Initialize the tool registry.
    
    Note: Tool definitions are now loaded dynamically from the extensions system.
    This function is kept for compatibility but no longer loads static definitions.
    """
    pass