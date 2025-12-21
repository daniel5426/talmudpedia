import asyncio
import aiohttp
import time
import random
from typing import Dict, Any, Optional, List
from aiohttp import ClientSession, TCPConnector


class AsyncSefariaClient:
    BASE_URL = "https://www.sefaria.org/api"

    def __init__(
        self, 
        max_retries: int = 5, 
        initial_backoff: float = 1.0,
        max_concurrent_requests: int = 50,
        rate_limit_per_second: int = 10
    ):
        """
        Async Sefaria API client with connection pooling and rate limiting.
        
        Args:
            max_retries: Maximum number of retry attempts
            initial_backoff: Initial backoff time in seconds
            max_concurrent_requests: Maximum concurrent connections
            rate_limit_per_second: Maximum requests per second
        """
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_concurrent_requests = max_concurrent_requests
        self.rate_limit_per_second = rate_limit_per_second
        
        # Semaphore for rate limiting
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        
        # Rate limiter
        self.last_request_time = 0
        self.min_request_interval = 1.0 / rate_limit_per_second
        self.rate_lock = asyncio.Lock()
        
        self._session: Optional[ClientSession] = None

    async def __aenter__(self):
        await self.create_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_session()

    async def create_session(self):
        """Create aiohttp session with connection pooling."""
        if self._session is None:
            connector = TCPConnector(
                limit=self.max_concurrent_requests,
                limit_per_host=self.max_concurrent_requests,
                ttl_dns_cache=300
            )
            timeout = aiohttp.ClientTimeout(total=60, connect=30)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={"User-Agent": "Talmudpedia-Ingestion/2.0-Async"}
            )

    async def close_session(self):
        """Close the aiohttp session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def _rate_limit(self):
        """Enforce rate limiting."""
        async with self.rate_lock:
            now = time.time()
            time_since_last = now - self.last_request_time
            if time_since_last < self.min_request_interval:
                await asyncio.sleep(self.min_request_interval - time_since_last)
            self.last_request_time = time.time()

    async def _get(
        self, 
        endpoint: str, 
        params: Optional[Dict] = None, 
        max_retries: Optional[int] = None
    ) -> Dict[str, Any]:
        """Make a GET request with retry logic and rate limiting."""
        if self._session is None:
            await self.create_session()
        
        url = f"{self.BASE_URL}{endpoint}"
        max_retries = max_retries or self.max_retries
        last_exception = None
        
        async with self.semaphore:
            for attempt in range(max_retries):
                try:
                    await self._rate_limit()
                    
                    async with self._session.get(url, params=params) as response:
                        if response.status == 200:
                            return await response.json()
                        
                        # Handle HTTP errors
                        is_retryable = response.status in [429, 500, 502, 503, 504]
                        
                        if not is_retryable or attempt == max_retries - 1:
                            if attempt == max_retries - 1:
                                print(f"Error fetching {url} (attempt {attempt + 1}/{max_retries}): HTTP {response.status}")
                            return {}
                        
                        backoff_time = self.initial_backoff * (2 ** attempt) + random.uniform(0, 1)
                        backoff_time = min(backoff_time, 60.0)
                        
                        if response.status == 503:
                            print(f"Service unavailable (503) for {url}. Retrying in {backoff_time:.2f}s (attempt {attempt + 1}/{max_retries})...")
                        elif response.status == 429:
                            print(f"Rate limit (429) for {url}. Retrying in {backoff_time:.2f}s (attempt {attempt + 1}/{max_retries})...")
                        else:
                            print(f"HTTP error {response.status} for {url}. Retrying in {backoff_time:.2f}s (attempt {attempt + 1}/{max_retries})...")
                        
                        await asyncio.sleep(backoff_time)
                        
                except asyncio.TimeoutError as e:
                    last_exception = e
                    if attempt == max_retries - 1:
                        print(f"Timeout error fetching {url} (attempt {attempt + 1}/{max_retries})")
                        return {}
                    
                    backoff_time = self.initial_backoff * (2 ** attempt) + random.uniform(0, 1)
                    backoff_time = min(backoff_time, 30.0)
                    print(f"Timeout for {url}. Retrying in {backoff_time:.2f}s (attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(backoff_time)
                    
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries - 1:
                        print(f"Error fetching {url} (attempt {attempt + 1}/{max_retries}): {e}")
                        return {}
                    
                    backoff_time = self.initial_backoff * (2 ** attempt) + random.uniform(0, 1)
                    backoff_time = min(backoff_time, 30.0)
                    print(f"Request error for {url}. Retrying in {backoff_time:.2f}s (attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(backoff_time)
        
        print(f"Failed to fetch {url} after {max_retries} attempts: {last_exception}")
        return {}

    async def get_index(self, index_title: str) -> Dict[str, Any]:
        """Fetch index metadata."""
        return await self._get(f"/v2/index/{index_title}")

    async def get_shape(self, index_title: str) -> List[Dict[str, Any]]:
        """Fetch the shape of the text."""
        return await self._get(f"/shape/{index_title}")

    async def get_related(self, tref: str) -> Dict[str, Any]:
        """Fetch related links for a given text reference."""
        return await self._get(f"/related/{tref}")

    async def get_text(self, tref: str, version: str = "primary") -> Dict[str, Any]:
        """Fetch text content."""
        params = {"version": version}
        return await self._get(f"/v3/texts/{tref}", params=params)

    async def get_all_titles(self) -> List[str]:
        """Fetch all index titles from Sefaria."""
        response = await self._get("/index/titles")
        return response.get("books", [])

    async def get_table_of_contents(self) -> List[Dict[str, Any]]:
        """Fetch the complete table of contents."""
        return await self._get("/index")

    async def fetch_multiple_texts(self, refs: List[str], version: str = "primary") -> List[Dict[str, Any]]:
        """Fetch multiple texts concurrently."""
        tasks = [self.get_text(ref, version) for ref in refs]
        return await asyncio.gather(*tasks)

    async def fetch_multiple_related(self, refs: List[str]) -> List[Dict[str, Any]]:
        """Fetch multiple related links concurrently."""
        tasks = [self.get_related(ref) for ref in refs]
        return await asyncio.gather(*tasks)
