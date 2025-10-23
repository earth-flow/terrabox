"""Tool override service for managing tool overrides and effective tool lists."""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from ...db.models import Connection as DBConnection, ToolOverride, Toolkit, ConnectionStatus
from ..tool_registry import get_tool_registry, ToolDefinition


class ToolOverrideService:
    """Service for managing tool overrides and effective tool lists."""
    
    @staticmethod
    def get_effective_tools(
        db: Session, 
        connection_id: str,
        include_disabled: bool = False
    ) -> Dict[str, Any]:
        """Get effective tools list for a connection (merged registry + overrides)."""
        connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        # Get toolkit to determine tool scope
        toolkit = db.query(Toolkit).filter(Toolkit.id == connection.toolkit_id).first()
        if not toolkit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Toolkit not found"
            )
        
        # Get tool definitions from registry
        registry = get_tool_registry()
        tool_defs = registry.list_tools(toolkit.key)
        
        # Get overrides for this connection
        overrides = db.query(ToolOverride).filter(
            ToolOverride.connection_id == connection_id
        ).all()
        override_map = {override.tool_key: override for override in overrides}
        
        # Merge tools with overrides
        effective_tools = []
        orphan_overrides = []
        
        for tool_def in tool_defs:
            override = override_map.get(tool_def.tool_key)
            
            # Calculate effective enabled state
            enabled = ToolOverrideService._calculate_enabled(
                tool_def, override, connection
            )
            
            # Skip disabled tools unless requested
            if not enabled and not include_disabled:
                continue
            
            # Merge configuration
            config = ToolOverrideService._merge_config(
                tool_def.default_config or {}, 
                override.config if override else {}
            )
            
            # Check if override is stale
            is_stale = bool(
                override and 
                override.resolved_digest and 
                override.resolved_digest != tool_def.digest
            )
            
            effective_tool = {
                "tool_key": tool_def.tool_key,
                "name": tool_def.name,
                "description": tool_def.description,
                "input_schema": tool_def.input_schema,
                "enabled": enabled,
                "config": config,
                "version": getattr(tool_def, 'version', None),
                "digest": tool_def.digest,
                "is_stale": is_stale,
                "required_scopes": tool_def.required_scopes
            }
            
            effective_tools.append(effective_tool)
        
        # Find orphan overrides (overrides without corresponding tool definitions)
        tool_keys = {tool_def.tool_key for tool_def in tool_defs}
        for override in overrides:
            if override.tool_key not in tool_keys:
                orphan_overrides.append({
                    "tool_key": override.tool_key,
                    "enabled": override.enabled,
                    "config": override.config,
                    "tool_version": override.tool_version,
                    "resolved_digest": override.resolved_digest
                })
        
        return {
            "tools": effective_tools,
            "orphan_overrides": orphan_overrides,
            "connection_id": str(connection_id),
            "toolkit_key": toolkit.key
        }
    
    @staticmethod
    def upsert_tool_override(
        db: Session,
        connection_id: str,
        tool_key: str,
        enabled: Optional[bool] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> ToolOverride:
        """Create or update a tool override."""
        # Validate that the tool exists in registry
        registry = get_tool_registry()
        tool_def = registry.get_tool(tool_key)
        if not tool_def:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tool '{tool_key}' not found in registry"
            )
        
        # Validate config against tool's input schema if provided
        if config:
            ToolOverrideService._validate_config(tool_def, config)
        
        # Get or create override
        override = db.query(ToolOverride).filter(
            ToolOverride.connection_id == connection_id,
            ToolOverride.tool_key == tool_key
        ).first()
        
        if override:
            # Update existing override
            if enabled is not None:
                override.enabled = enabled
            if config is not None:
                override.config = config
            override.tool_version = None  # ToolDefinition doesn't have version attribute
            override.resolved_digest = tool_def.digest
            override.is_stale = False
        else:
            # Create new override
            override = ToolOverride(
                connection_id=connection_id,
                tool_key=tool_key,
                enabled=enabled,
                config=config or {},
                tool_version=None,  # ToolDefinition doesn't have version attribute
                resolved_digest=tool_def.digest,
                is_stale=False
            )
            db.add(override)
            db.flush()  # This will assign the ID
        
        db.commit()
        db.refresh(override)
        
        return override
    
    @staticmethod
    def delete_tool_override(
        db: Session,
        connection_id: str,
        tool_key: str
    ) -> bool:
        """Delete a tool override."""
        override = db.query(ToolOverride).filter(
            ToolOverride.connection_id == connection_id,
            ToolOverride.tool_key == tool_key
        ).first()
        
        if override:
            db.delete(override)
            db.commit()
            return True
        
        return False
    
    @staticmethod
    def mark_stale_overrides(
        db: Session,
        tool_key: str,
        new_digest: str
    ) -> int:
        """Mark overrides as stale when tool definition changes."""
        count = db.query(ToolOverride).filter(
            ToolOverride.tool_key == tool_key,
            ToolOverride.resolved_digest != new_digest,
            ToolOverride.resolved_digest.isnot(None)
        ).update({
            "is_stale": True
        })
        
        db.commit()
        return count
    
    @staticmethod
    def _calculate_enabled(
        tool_def: ToolDefinition,
        override: Optional[ToolOverride],
        connection: DBConnection
    ) -> bool:
        """Calculate effective enabled state for a tool."""
        # Start with override or default
        enabled = (
            override.enabled if override and override.enabled is not None 
            else tool_def.default_enabled
        )
        
        # Must be connection enabled and valid
        enabled = enabled and connection.enabled and connection.status == ConnectionStatus.valid
        
        # Check required scopes
        if tool_def.required_scopes and connection.scopes:
            required_scopes = set(tool_def.required_scopes)
            granted_scopes = set(connection.scopes)
            if not required_scopes.issubset(granted_scopes):
                enabled = False
        
        return enabled
    
    @staticmethod
    def _merge_config(
        default_config: Dict[str, Any],
        override_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Deep merge default config with override config."""
        import copy
        
        result = copy.deepcopy(default_config)
        
        def deep_merge(target: Dict, source: Dict):
            for key, value in source.items():
                if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                    deep_merge(target[key], value)
                else:
                    target[key] = value
        
        deep_merge(result, override_config)
        return result
    
    @staticmethod
    def _validate_config(
        tool_def: ToolDefinition,
        config: Dict[str, Any]
    ) -> None:
        """Validate config against tool's input schema."""
        # TODO: Implement JSON Schema validation
        # For now, just basic type checking
        if not isinstance(config, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Config must be a JSON object"
            )