"""Example toolkit plugin demonstrating the plugin system.

This module shows how to create a toolkit plugin that registers
itself with the Terralink platform. It includes a simple example
tool that demonstrates the plugin registration process.
"""

from ..core.registry import ToolSpec


def echo_handler(arguments: dict, context: dict, account=None):
    """Simple echo tool that returns the input message.
    
    This is a demonstration tool that shows how handlers work
    in the plugin system.
    """
    message = arguments.get("message", "Hello, World!")
    return {
        "echo": message,
        "user_id": context.get("user_id"),
        "timestamp": "2024-01-01T00:00:00Z"
    }


def math_add_handler(arguments: dict, context: dict, account=None):
    """Simple math tool that adds two numbers.
    
    Demonstrates a more complex tool with validation.
    """
    try:
        a = float(arguments.get("a", 0))
        b = float(arguments.get("b", 0))
        result = a + b
        return {
            "result": result,
            "operation": f"{a} + {b} = {result}"
        }
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid input: {e}")


def setup(registrar):
    """Plugin setup function called by the platform.
    
    This function is the entry point for the plugin. It registers
    the toolkit and all its tools with the platform.
    
    Parameters
    ----------
    registrar : Registrar
        The registrar instance provided by the platform
    """
    # Register the toolkit
    registrar.toolkit(
        name="example",
        description="Example toolkit demonstrating the plugin system",
        version="1.0.0"
    )
    
    # Register the echo tool
    echo_spec = ToolSpec(
        slug="example.echo",
        name="Echo",
        description="Echo back a message",
        parameters={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message to echo back"
                }
            },
            "required": []
        },
        requires_connection=True
    )
    registrar.tool(echo_spec, echo_handler)
    
    # Register the math add tool
    math_add_spec = ToolSpec(
        slug="example.math_add",
        name="Math Add",
        description="Add two numbers together",
        parameters={
            "type": "object",
            "properties": {
                "a": {
                    "type": "number",
                    "description": "First number to add"
                },
                "b": {
                    "type": "number", 
                    "description": "Second number to add"
                }
            },
            "required": ["a", "b"]
        },
        requires_connection=False
    )
    registrar.tool(math_add_spec, math_add_handler)