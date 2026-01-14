"""Plugin system for the Terralink platform.

This module provides the infrastructure for loading and registering
toolkits and tools from both built-in modules and external packages.
Plugins can register themselves through entry points or by placing
modules in the toolkits/ directory.
"""

from __future__ import annotations

import logging
from importlib import import_module
from importlib.metadata import entry_points
from pathlib import Path
from typing import Callable, Optional

from .core.registry import register_tool, register_toolkit, get_handler as _get_handler
from .core.registry import ToolSpec, ToolDefinition as Toolkit

logger = logging.getLogger(__name__)


class Registrar:
    """API for plugins to register toolkits and tools.
    
    This class provides a clean interface for plugins to register
    their toolkits and tools with the platform. It acts as a bridge
    between the plugin system and the internal data storage.
    """
    
    def toolkit(self, name: str, description: str, version: str = "1.0"):
        """Register a toolkit with the platform.
        
        Parameters
        ----------
        name : str
            Unique name for the toolkit
        description : str
            Human-readable description of the toolkit
        version : str, optional
            Version of the toolkit, defaults to "1.0"
        """
        register_toolkit(name, description, version)
    
    def tool(self, spec: ToolSpec, handler: Callable):
        """Register a tool with the platform.
        
        Parameters
        ----------
        spec : ToolSpec
            Tool specification containing slug, description, parameters, etc.
        handler : Callable
            Function that will be called to execute the tool
        """
        register_tool(spec, handler)


def get_handler(slug: str) -> Callable | None:
    """Get the handler function for a tool by its slug.
    
    Parameters
    ----------
    slug : str
        The tool slug to look up
        
    Returns
    -------
    Callable | None
        The handler function if found, None otherwise
    """
    return _get_handler(slug)


def load_builtin_toolkits():
    """Load built-in toolkits from the toolkits/ directory.
    
    This function scans the toolkits/ directory for Python modules
    and loads any that have a setup() function. This allows for
    built-in toolkits to be organized in separate modules.
    """
    base = Path(__file__).resolve().parent / "toolkits"
    if not base.exists():
        return
    
    for py in base.glob("*.py"):
        if py.name.startswith("_"):
            continue
        
        try:
            mod = import_module(f"{__package__}.toolkits.{py.stem}")
            if hasattr(mod, "setup"):
                mod.setup(Registrar())
        except ImportError as e:
            logger.warning(f"Failed to load builtin toolkit {py.stem}: {e}")


def load_entrypoint_plugins(group: str = "terralink.toolkits"):
    """Load external plugins through Python entry points.
    
    This function discovers and loads plugins that have registered
    themselves through setuptools entry points. This allows third-party
    packages to extend the platform with new toolkits.
    
    Parameters
    ----------
    group : str, optional
        The entry point group to search for plugins
    """
    try:
        eps = entry_points(group=group)
    except TypeError:
        # Compatibility with Python < 3.10
        eps = entry_points().get(group, [])
    
    for ep in eps:
        try:
            setup_fn = ep.load()
            setup_fn(Registrar())  # Convention: plugins expose setup(registrar)
        except Exception as e:
            logger.warning(f"Failed to load plugin {ep.name}: {e}")