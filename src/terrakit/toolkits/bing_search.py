import os
import json
import time
import queue
import atexit
import pathlib
import threading
try:
    import aiohttp
except ImportError:
    # Mock aiohttp for testing
    class aiohttp:
        class ClientSession:
            pass
import asyncio
from typing import Optional, Union, Dict, List, Any
from urllib.parse import urlencode
try:
    import regex as re
except ImportError:
    # Fallback to standard re module if regex is not available
    import re

try:
    import langid
except ImportError:
    # Mock langid for testing
    class langid:
        @staticmethod
        def classify(text):
            return ('en', 1.0)

from ..core.tool_registry import ToolSpec

class BingSearchEngine():
    """
    Async Bing search engine that provides web search capability with caching.
    
    This tool interfaces with the Brightdata API to perform Bing searches.
    It includes robust caching to minimize redundant API calls and supports
    asynchronous operations with connection pooling.
    """

    def __init__(
        self,
        api_key: str,
        zone: str = "serp_api1",
        max_results: int = 10,
        result_length: int = 1000,
        location: str = "us",
        cache_file: Optional[str] = None,
        cache_refresh_interval: float = 15.0
    ):
        """
        Initialize the Bing search engine.
        
        Args:
            api_key: Brightdata API key
            zone: Brightdata zone name
            max_results: Maximum number of search results to return
            result_length: Maximum length of each result snippet
            location: Country code for search localization
            cache_file: Path to cache file (if None, uses ~/.verl_cache/bing_search_cache.jsonl)
            cache_refresh_interval: Minimum seconds between cache file checks
        """
        # API configuration
        self._api_key = api_key
        self._zone = zone
        self._max_results = max_results
        self._result_length = result_length
        self._location = location
        
        # Cache and synchronization
        self._cache = {}
        self._cache_lock = threading.Lock()
        self._lang_id_lock = threading.Lock()
        self._cache_refresh_interval = cache_refresh_interval
        self._last_cache_check = 0.0
        self._cache_mod_time = 0.0
        
        # Setup cache file paths
        self._setup_cache_paths(cache_file)
        
        # Load existing cache
        self._load_cache()
        
        # HTTP session for connection pooling
        self._session = None
    
    def _setup_cache_paths(self, cache_file: Optional[str]) -> None:
        """
        Set up cache file path.
        
        Args:
            cache_file: Path to cache file or None for default
        """
        if cache_file is None:
            cache_dir = pathlib.Path.home() / ".verl_cache"
            cache_dir.mkdir(exist_ok=True)
            self._cache_file = cache_dir / "bing_search_cache.jsonl"
        else:
            self._cache_file = pathlib.Path(cache_file)
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_cache(self) -> None:
        """Load the cache from JSONL file."""
        if not self._cache_file.exists():
            return
            
        try:
            # Record file modification time
            self._cache_mod_time = os.path.getmtime(self._cache_file)
            
            # Load JSONL file line by line
            cache_data = {}
            with open(self._cache_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if 'query' in entry and 'result' in entry:
                            cache_data[entry['query']] = entry['result']
                        else:
                            print(f"Invalid cache entry format at line {line_num}")
                    except json.JSONDecodeError as e:
                        print(f"Invalid JSON at line {line_num}: {e}")
                        continue
            
            # Update in-memory cache
            with self._cache_lock:
                self._cache = cache_data
            
            self._last_cache_check = time.time()
            print(f"Loaded {len(self._cache)} cache entries from {self._cache_file}")
            
        except Exception as e:
            print(f"Failed to load cache file: {str(e)}")
            self._cache = {}

    async def _save_cache_async(self, query: str, result: str) -> None:
        """Save a single cache entry to JSONL file asynchronously."""
        if query is None or result is None:
            return
            
        def _write_cache():
            try:
                # Create cache entry
                cache_entry = {
                    "query": query,
                    "result": result,
                    "timestamp": time.time()
                }
                
                # Append to JSONL file
                with open(self._cache_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(cache_entry, ensure_ascii=False) + "\n")
                
                # Update modification time record
                self._cache_mod_time = os.path.getmtime(self._cache_file)
                    
            except Exception as e:
                print(f"Failed to save cache entry: {str(e)}")
        
        # Run cache write in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _write_cache)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with connection pooling."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,  # Total connection pool size
                limit_per_host=30,  # Max connections per host
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={'User-Agent': 'AsyncBingSearchEngine/1.0'}
            )
        return self._session

    @property
    def name(self) -> str:
        """Tool name identifier."""
        return "bing_search"

    @property
    def trigger_tag(self) -> str:
        """Tag used to trigger this tool."""
        return "search"

    async def _make_request(self, query: str, timeout: int) -> Dict:
        """
        Send async request to Brightdata API.

        Args:
            query: Search query
            timeout: Request timeout in seconds

        Returns:
            API response data as dict
        """
        # Determine language settings based on query language
        with self._lang_id_lock:
            lang_code, lang_confidence = langid.classify(query)
        if lang_code == 'zh':
            mkt, setLang = "zh-CN", "zh"
        else:
            mkt, setLang = "en-US", "en"
        
        # Prepare URL with query parameters
        encoded_query = urlencode({
            "q": query, 
            "mkt": mkt, 
            "setLang": setLang
        })
        target_url = f"https://www.bing.com/search?{encoded_query}&brd_json=1&cc={self._location}"

        # Prepare headers and payload
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "zone": self._zone,
            "url": target_url,
            "format": "raw"
        }

        # Get session and make async request
        session = await self._get_session()
        
        async with session.post(
            "https://api.brightdata.com/request",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            if response.status != 200:
                text = await response.text()
                raise Exception(f"HTTP {response.status}: {text}")
            
            response_text = await response.text()
            return json.loads(response_text)

    async def execute(self, query: str, timeout: int = 60) -> str:
        """
        Execute Bing search query asynchronously.

        Args:
            query: Search query string
            timeout: API request timeout in seconds

        Returns:
            Formatted search results as string
        """
        # Clean query
        query = query.replace('"', '')
        
        # Check cache for existing results
        with self._cache_lock:
            if query in self._cache:
                print(f"Cache hit for query: {query}")
                return self._cache[query]

        try:
            # Make async API request
            data = await self._make_request(query, timeout)

            # Extract search results
            result = self._extract_and_format_results(data)
            
            # Update cache
            with self._cache_lock:
                self._cache[query] = result
            
            # Save cache asynchronously
            await self._save_cache_async(query, result)
                
            return result

        except asyncio.TimeoutError:
            error_msg = f"Bing search request timed out after {timeout} seconds"
            print(error_msg)
            return f"Search failed: {error_msg}"
        except Exception as e:
            error_msg = f"Bing search failed: {str(e)}"
            print(error_msg)
            return f"Search failed: {error_msg}"
    
    def _extract_and_format_results(self, data: Dict) -> str:
        """
        Extract and format search results from API response.
        
        Args:
            data: API response data
            
        Returns:
            Formatted search results as string
        """
        # If no organic results, return empty response
        if 'organic' not in data:
            data['chunk_content'] = []
            return self._format_results(data)

        # Extract unique snippets
        chunk_content_list = []
        seen_snippets = set()
        for result in data['organic']:
            snippet = result.get('description', '').strip()
            if len(snippet) > 0 and snippet not in seen_snippets:
                chunk_content_list.append(snippet)
                seen_snippets.add(snippet)

        data['chunk_content'] = chunk_content_list
        return self._format_results(data)

    def _format_results(self, results: Dict) -> str:
        """
        Format search results into readable text.
        
        Args:
            results: Dictionary containing search results
            
        Returns:
            Formatted string of search results
        """
        if not results.get("chunk_content"):
            return "No search results found."

        formatted = []
        for idx, snippet in enumerate(results["chunk_content"][:self._max_results], 1):
            snippet = snippet[:self._result_length]
            formatted.append(f"Page {idx}: {snippet}")
        
        return "\n".join(formatted)

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()


def bing_search_handler(arguments: dict, context: dict, account=None) -> Dict[str, Any]:
    """
    Bing search handler function for Terrakit plugin system.
    
    Args:
        arguments: Tool arguments containing search parameters
        context: Execution context (user_id, etc.)
        account: Optional account information
        
    Returns:
        Dict containing search results or error information
    """
    try:
        # Extract search parameters
        query = arguments.get("query", "")
        max_results = int(arguments.get("max_results", 10))
        result_length = int(arguments.get("result_length", 1000))
        location = arguments.get("location", "cn")
        timeout = int(arguments.get("timeout", 60))
        
        # Validate required parameters
        if not query:
            return {
                "success": False,
                "error": "Search query is required",
                "query": query
            }
        
        # Get API key from environment or arguments
        api_key = arguments.get("api_key") or os.getenv('BRIGHTDATA_API_KEY')
        if not api_key:
            return {
                "success": False,
                "error": "API key must be provided either as parameter or BRIGHTDATA_API_KEY environment variable",
                "query": query
            }
        
        # Initialize search engine
        search_engine = BingSearchEngine(
            api_key=api_key,
            max_results=max_results,
            result_length=result_length,
            location=location
        )
        
        # Create new event loop for async execution
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Execute search
            search_results = loop.run_until_complete(search_engine.execute(query, timeout))
            
            # Process results
            if search_results and not search_results.startswith("Search failed:"):
                return {
                    "success": True,
                    "query": query,
                    "results": search_results,
                    "result_count": len(search_results.split('\n')) if search_results else 0
                }
            else:
                return {
                    "success": False,
                    "error": search_results or "Search returned no results",
                    "query": query
                }
                
        finally:
            # Cleanup event loop
            loop.close()
            # Cleanup search engine session
            if hasattr(search_engine, '_session') and search_engine._session and not search_engine._session.closed:
                try:
                    close_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(close_loop)
                    close_loop.run_until_complete(search_engine.close())
                    close_loop.close()
                except:
                    pass  # Best effort cleanup
                    
    except Exception as e:
        return {
            "success": False,
            "error": f"Search failed with error: {str(e)}",
            "query": arguments.get("query", "")
        }


def setup(registrar):
    """
    Setup function for Bing Search toolkit plugin.
    
    This function registers the Bing Search toolkit and its tools with the Terrakit plugin system.
    
    Args:
        registrar: The registrar object used to register toolkits and tools
    """
    # Register the toolkit
    registrar.toolkit(
        name="bing_search",
        description="Bing search toolkit for web search functionality",
        version="1.0.0"
    )
    
    # Define the Bing search tool specification
    bing_search_spec = ToolSpec(
        slug="bing_search.search",
        name="Bing Search",
        description="Perform web searches using Bing search engine via Brightdata API",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of search results to return (default: 10)",
                    "default": 10
                },
                "result_length": {
                    "type": "integer",
                    "description": "Maximum length of each result snippet (default: 1000)",
                    "default": 1000
                },
                "location": {
                    "type": "string",
                    "description": "Country code for search localization (default: cn)",
                    "default": "cn"
                },
                "timeout": {
                    "type": "integer",
                    "description": "API request timeout in seconds (default: 60)",
                    "default": 60
                },
                "api_key": {
                    "type": "string",
                    "description": "Brightdata API key (optional, can use BRIGHTDATA_API_KEY env var)"
                }
            },
            "required": ["query"]
        },
        requires_connection=True
    )
    
    # Register the tool with its handler
    registrar.tool(bing_search_spec, bing_search_handler)
