import logging
from typing import List, Any, Dict
from mcp.server import Server
from mcp.types import Tool, TextContent
from terrakit.core.services import ToolService
from terrakit.core.schemas import ExecuteRequestIn
from terrakit.db.session import SessionLocal
from terrakit.db import models as m

logger = logging.getLogger(__name__)

class TerraKitMCPServer:
    def __init__(self):
        self.server = Server("terrakit")
        
        @self.server.list_tools()
        async def list_tools(**kwargs) -> List[Tool]:
            logger.info(f"MCP: list_tools called with args: {kwargs}")
            db = SessionLocal()
            try:
                # Use the first active user as the context for tool discovery
                # In a real scenario, we might want to pass the API key in the initialization options
                user = db.query(m.User).filter(m.User.is_active == True).first()
                user_id = user.user_id if user else "system"
                
                tools = ToolService.get_tools_with_status(db, user_id)
                
                mcp_tools = []
                for t in tools:
                    if t.status != "available":
                        continue
                    mcp_tools.append(
                        Tool(
                            name=t.slug.replace(".", "_"),
                            description=t.description,
                            inputSchema=t.parameters or {"type": "object", "properties": {}}
                        )
                    )
                return mcp_tools
            except Exception as e:
                logger.error(f"Error listing tools: {e}")
                return []
            finally:
                db.close()

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> List[TextContent]:
            db = SessionLocal()
            try:
                user = db.query(m.User).filter(m.User.is_active == True).first()
                if not user:
                    return [TextContent(type="text", text="Error: No active user found for execution.")]
                
                # Resolve slug (underscores -> dots)
                real_slug = name
                if "." not in name:
                    tools = ToolService.get_tools_with_status(db, user.user_id)
                    for t in tools:
                        if t.slug.replace(".", "_") == name:
                            real_slug = t.slug
                            break
                
                # Execute
                req = ExecuteRequestIn(inputs=arguments if isinstance(arguments, dict) else {})
                result = await ToolService.execute_tool(db, user.user_id, real_slug, req)
                
                if result.success:
                    return [TextContent(type="text", text=str(result.outputs))]
                else:
                    return [TextContent(type="text", text=f"Error: {result.error}")]
            except Exception as e:
                logger.error(f"Error executing tool {name}: {e}")
                return [TextContent(type="text", text=f"Exception: {str(e)}")]
            finally:
                db.close()

# Global instance
mcp_instance = TerraKitMCPServer()
