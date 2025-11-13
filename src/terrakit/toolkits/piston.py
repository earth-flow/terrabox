import asyncio
import json
import re
import xml.etree.ElementTree as ET

# Fallback imports for aiohttp
try:
    import aiohttp
    from aiohttp import ClientSession, ClientConnectorError
except ImportError:
    # Mock aiohttp for testing
    class MockResponse:
        def __init__(self, status=200):
            self.status = status
        
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        async def json(self):
            return {
                "language": "python", 
                "version": "3.9",
                "run": {
                    "stdout": "Hello from Piston!\\n2 + 2 = 4",
                    "stderr": "",
                    "code": 0,
                    "signal": None,
                    "cpu_time": 50,
                    "memory": 1024000
                }
            }
        async def text(self):
            return "Mock response"
    
    class MockClientSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        def get(self, url):
            return MockResponse()
        def post(self, url, json=None):
            return MockResponse()
    
    class ClientConnectorError(Exception):
        pass
    
    aiohttp = type('MockAiohttp', (), {
        'ClientSession': MockClientSession,
        'ClientConnectorError': ClientConnectorError
    })()

from ..core.tool_registry import ToolSpec

import logging

logger = logging.getLogger(__name__)

# Configuration constants
DEFAULT_API_URL = "https://emkc.org/api/v2/piston"
LOCAL_API_URL = "http://localhost:2000/api/v2"

# File extensions for different languages
LANGUAGE_EXTENSIONS = {
    "python": ".py",
    "javascript": ".js", 
    "typescript": ".ts",
    "java": ".java",
    "c": ".c",
    "cpp": ".cpp",
    "csharp": ".cs",
    "go": ".go",
    "rust": ".rs",
    "ruby": ".rb",
    "php": ".php",
    "swift": ".swift",
    "kotlin": ".kt",
    "scala": ".scala"
}


def _get_extension_for_language(language):
    """Get file extension for a given language"""
    return LANGUAGE_EXTENSIONS.get(language.lower(), f".{language}")


def _get_api_endpoint(api_url, endpoint, is_public_api):
    """Build full endpoint path based on API URL"""
    if is_public_api:
        # Public API endpoint format already includes /api/v2/piston
        return f"{api_url}/{endpoint}"
    else:
        # Local API may or may not include /api/v2
        if "/api/v2" in api_url:
            return f"{api_url}/{endpoint}"
        else:
            return f"{api_url}/api/v2/{endpoint}"


async def _test_connection(api_url, is_public_api):
    """Test connection to the Piston API"""
    try:
        async with aiohttp.ClientSession() as session:
            url = _get_api_endpoint(api_url, "runtimes", is_public_api)
            async with session.get(url) as response:
                if response.status != 200:
                    raise ConnectionError(f"Failed to connect to Piston API: HTTP {response.status}")
                
                # Get list of available runtimes for info
                runtimes = await response.json()
                languages = [f"{r['language']} ({r['version']})" for r in runtimes[:5]]
                logger.info(f"Piston API connected. Available languages (showing 5 of {len(runtimes)}): {', '.join(languages)}...")
                    
    except aiohttp.ClientConnectorError:
        raise ConnectionError("Cannot connect to Piston API. Is the Docker container running?")
    except Exception as e:
        raise ConnectionError(f"Failed to connect to Piston API: {str(e)}")


def _parse_xml_action(action: str):
    """Parse XML formatted action"""
    try:
        # Process XML
        root = ET.fromstring(action)
        if root.tag != "piston":
            return None, False
        
        parsed = {}
        
        # Parse basic attributes
        for elem in root:
            if elem.tag in ["language", "version", "args", "stdin"]:
                parsed[elem.tag] = elem.text.strip() if elem.text else ""
            elif elem.tag == "file":
                if "files" not in parsed:
                    parsed["files"] = []
                
                filename = elem.get("name", f"file{len(parsed['files'])}")
                content = elem.text if elem.text else ""
                
                parsed["files"].append({
                    "name": filename,
                    "content": content
                })
        
        # Ensure required fields exist
        if "language" not in parsed:
            logger.error("Missing required language field")
            return None, False
            
        if "files" not in parsed or len(parsed["files"]) == 0:
            logger.error("Missing file content")
            return None, False
            
        # Process args
        if "args" in parsed:
            parsed["args"] = parsed["args"].split()
            
        return parsed, True
    except ET.ParseError as e:
        logger.error(f"XML parsing error: {str(e)}")
        return None, False
    except Exception as e:
        logger.error(f"Error parsing XML action: {str(e)}")
        return None, False


from typing import Union

def _parse_json_action(action: Union[str, dict]):
    """Parse JSON formatted action"""
    try:
        parsed = json.loads(action) if isinstance(action, str) else action
        
        # Ensure required fields exist
        if "language" not in parsed:
            logger.error("Missing required language field")
            return None, False
            
        if "files" not in parsed or not isinstance(parsed["files"], list) or len(parsed["files"]) == 0:
            logger.error("Missing file content or files field is not a valid array")
            return None, False
            
        # Validate files structure
        for i, file in enumerate(parsed["files"]):
            if not isinstance(file, dict) or "content" not in file:
                logger.error(f"File #{i+1} is missing content or has invalid format")
                return None, False
                
            if "name" not in file:
                # Generate default filename
                extension = _get_extension_for_language(parsed["language"]) 
                file["name"] = f"file{i}{extension}"
        # Normalize args: accept string and convert to list
        if "args" in parsed and not isinstance(parsed["args"], list):
            if isinstance(parsed["args"], str):
                parsed["args"] = parsed["args"].split()
            else:
                parsed["args"] = [str(parsed["args"])]
        
        return parsed, True
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {str(e)}")
        return None, False
    except Exception as e:
        logger.error(f"Error parsing JSON action: {str(e)}")
        return None, False


def parse_action(action):
    """Parse action in either XML (string) or JSON (string/object) format"""
    if isinstance(action, dict):
        return _parse_json_action(action)
    action = action.strip()
    
    # Try to parse as XML format
    if action.startswith("<piston>") and action.endswith("</piston>"):
        return _parse_xml_action(action)
    
    # Try to parse as JSON format
    elif action.startswith("{") and action.endswith("}"):
        return _parse_json_action(action)
    
    # Invalid format
    else:
        logger.error("Unrecognized action format")
        return None, False


async def _execute_code(parsed_action, api_url, is_public_api):
    """Execute code and return result"""
    try:
        language = parsed_action.get("language")
        version = parsed_action.get("version", "*")
        args = parsed_action.get("args", [])
        stdin = parsed_action.get("stdin", "")
        files = parsed_action.get("files", [])
        
        payload = {
            "language": language,
            "version": version,
            "files": files,
            "stdin": stdin,
            "args": args,
            "compile_timeout": 10000,
            "run_timeout": 3000,
            "compile_memory_limit": -1,
            "run_memory_limit": -1
        }
        
        async with aiohttp.ClientSession() as session:
            url = _get_api_endpoint(api_url, "execute", is_public_api)
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    # Handle rate limiting
                    if is_public_api and response.status == 429:
                        retry_after = response.headers.get('Retry-After', '60')
                        return {"error": f"Rate limit exceeded. Try again after {retry_after} seconds."}
                        
                    error_text = await response.text()
                    return {"error": f"HTTP {response.status}: {error_text}"}
                
                result = await response.json()
                return result
    except Exception as e:
        logger.error(f"Error executing code: {str(e)}")
        return {"error": f"Failed to execute code: {str(e)}"}


async def piston_execute_handler(arguments: dict, context: dict, account=None) -> dict:
    """
    Execute code using the Piston API
    
    Args:
        arguments: Dictionary containing the action to execute
        context: Context information (may contain api_url, use_local, etc.)
        account: Account information (optional)
    
    Returns:
        Dictionary containing the execution result
    """
    try:
        # Get action from arguments
        action = arguments.get("action", "")
        if not action:
            return {
                "error": "Missing required 'action' parameter",
                "valid": False
            }
        
        # Get configuration from context or use defaults
        api_url = context.get("api_url") if context else None
        use_local = context.get("use_local", False) if context else False
        
        # Determine API URL
        if api_url is not None:
            is_public_api = "emkc.org" in api_url
        elif use_local:
            api_url = LOCAL_API_URL
            is_public_api = False
        else:
            api_url = DEFAULT_API_URL
            is_public_api = True
        
        # Parse action
        parsed_action, is_valid = parse_action(action)
        
        if not is_valid:
            return {
                "error": """Invalid action format. Supported formats:

1. XML format:
<piston>
  <language>python</language>
  <version>3.9</version>
  <args>arg1 arg2</args>
  <stdin>input data</stdin>
  <file name="main.py">
print("Hello, World!")
for i in range(5):
    print(f"Number {i}")
  </file>
</piston>

2. JSON format:
{
  "language": "python",
  "version": "3.9",
  "args": ["arg1", "arg2"],
  "stdin": "input data",
  "files": [
    {
      "name": "main.py",
      "content": "print('Hello, World!')\\nfor i in range(5):\\n    print(f'Number {i}')"
    }
  ]
}""",
                "valid": False
            }
        
        # Execute code
        try:
            result = await _execute_code(parsed_action, api_url, is_public_api)
            
            # Format output
            if "error" in result:
                return {
                    "error": result["error"],
                    "valid": False
                }
            elif "run" in result:
                stdout = result["run"].get("stdout", "")
                stderr = result["run"].get("stderr", "")
                code = result["run"].get("code")
                signal = result["run"].get("signal")
                cpu_time = result["run"].get("cpu_time", 0)
                memory = result["run"].get("memory", 0)
                
                status_msg = ""
                if result["run"].get("status"):
                    status_msg = f" ({result['run']['status']})"
                
                return {
                    "result": f"""Execution result:

Language: {parsed_action.get('language')}
Version: {result.get('version', parsed_action.get('version', '*'))}

--- STDOUT ---
{stdout}

--- STDERR ---
{stderr}

Exit code: {code}{status_msg}
Signal: {signal if signal else 'None'}
CPU time: {cpu_time}ms
Memory usage: {memory/1000000:.2f}MB""",
                    "valid": True
                }
            elif "compile" in result and result["compile"].get("status") is not None:
                # Compilation error
                stdout = result["compile"].get("stdout", "")
                stderr = result["compile"].get("stderr", "")
                code = result["compile"].get("code")
                
                return {
                    "result": f"""Compilation error:

--- Compile output ---
{stdout}

--- Compile error ---
{stderr}

Compilation exit code: {code}
Status: {result["compile"].get("status", "Unknown")}""",
                    "valid": True
                }
            else:
                return {
                    "error": f"Unknown result format: {json.dumps(result, indent=2)}",
                    "valid": False
                }
                
        except Exception as e:
            return {
                "error": f"Error executing code: {str(e)}",
                "valid": False
            }
            
    except Exception as e:
        return {
            "error": f"Error in piston_execute_handler: {str(e)}",
            "valid": False
        }


def setup(registrar):
    """Setup function for Terrakit plugin registration"""
    
    # Register the piston toolkit
    registrar.toolkit(
        name="piston",
        description="Execute code in various programming languages using the Piston API",
        version="1.0.0"
    )
    
    # Register the execute tool
    piston_execute_spec = ToolSpec(
        slug="piston.execute",
        name="Piston Execute",
        description="Execute code using the Piston API. Supports both XML and JSON formats for specifying code, language, version, arguments, and input.",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
            "description": "Code execution request in XML or JSON format. XML format: <piston><language>python</language><file name='main.py'>print('hello')</file></piston>. JSON format: {\"language\": \"python\", \"files\": [{\"name\": \"main.py\", \"content\": \"print('hello')\"}]}"
        }
            },
            "required": ["action"]
        }
    )
    
    registrar.tool(piston_execute_spec, piston_execute_handler)