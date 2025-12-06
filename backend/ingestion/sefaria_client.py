import requests
import time
import random
from typing import Dict, Any, Optional, List

class SefariaClient:
    BASE_URL = "https://www.sefaria.org/api"

    def __init__(self, max_retries: int = 5, initial_backoff: float = 1.0):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Talmudpedia-Ingestion/1.0"
        })
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff

    def _get(self, endpoint: str, params: Optional[Dict] = None, max_retries: Optional[int] = None) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{endpoint}"
        max_retries = max_retries or self.max_retries
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError as e:
                last_exception = e
                status_code = e.response.status_code if e.response else None
                error_str = str(e).lower()
                
                is_retryable = (
                    status_code in [429, 500, 502, 503, 504] or
                    "503" in error_str or
                    "502" in error_str or
                    "504" in error_str or
                    "500" in error_str or
                    "429" in error_str or
                    "service unavailable" in error_str or
                    "bad gateway" in error_str or
                    "gateway timeout" in error_str
                )
                
                if not is_retryable or attempt == max_retries - 1:
                    if attempt == max_retries - 1:
                        print(f"Error fetching {url} (attempt {attempt + 1}/{max_retries}): {e}")
                    return {}
                
                backoff_time = self.initial_backoff * (2 ** attempt) + random.uniform(0, 1)
                backoff_time = min(backoff_time, 60.0)
                
                if status_code == 503:
                    print(f"Service unavailable (503) for {url}. Retrying in {backoff_time:.2f} seconds (attempt {attempt + 1}/{max_retries})...")
                elif status_code == 429:
                    print(f"Rate limit (429) for {url}. Retrying in {backoff_time:.2f} seconds (attempt {attempt + 1}/{max_retries})...")
                else:
                    print(f"HTTP error {status_code} for {url}. Retrying in {backoff_time:.2f} seconds (attempt {attempt + 1}/{max_retries})...")
                
                time.sleep(backoff_time)
                
            except requests.exceptions.Timeout as e:
                last_exception = e
                if attempt == max_retries - 1:
                    print(f"Timeout error fetching {url} (attempt {attempt + 1}/{max_retries}): {e}")
                    return {}
                
                backoff_time = self.initial_backoff * (2 ** attempt) + random.uniform(0, 1)
                backoff_time = min(backoff_time, 30.0)
                print(f"Timeout for {url}. Retrying in {backoff_time:.2f} seconds (attempt {attempt + 1}/{max_retries})...")
                time.sleep(backoff_time)
                
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt == max_retries - 1:
                    print(f"Error fetching {url} (attempt {attempt + 1}/{max_retries}): {e}")
                    return {}
                
                backoff_time = self.initial_backoff * (2 ** attempt) + random.uniform(0, 1)
                backoff_time = min(backoff_time, 30.0)
                print(f"Request error for {url}. Retrying in {backoff_time:.2f} seconds (attempt {attempt + 1}/{max_retries})...")
                time.sleep(backoff_time)
        
        print(f"Failed to fetch {url} after {max_retries} attempts: {last_exception}")
        return {}

    def get_index(self, index_title: str) -> Dict[str, Any]:
        """
        Fetch index metadata (titles, categories, schema structure).
        Endpoint: /api/v2/index/{index_title}
        """
        return self._get(f"/v2/index/{index_title}")

    def get_shape(self, index_title: str) -> List[Dict[str, Any]]:
        """
        Fetch the shape of the text (jagged array structure).
        Endpoint: /api/shape/{index_title}
        """
        return self._get(f"/shape/{index_title}")

    def get_related(self, tref: str) -> Dict[str, Any]:
        """
        Fetch related links for a given text reference (tref).
        Endpoint: /api/related/{tref}
        """
        return self._get(f"/related/{tref}")

    def get_text(self, tref: str, version: str = "primary") -> Dict[str, Any]:
        """
        Fetch text content.
        Endpoint: /api/v3/texts/{tref}
        """
        params = {"version": version}
        result = self._get(f"/v3/texts/{tref}", params=params)
        
        if "Shulchan_Arukh, Even HaEzer.23" in tref or "Even_HaEzer.23" in tref:
            print(f"\n[DEBUG] API Call for {tref}")
            print(f"[DEBUG] Version parameter: {version}")
            print(f"[DEBUG] Response keys: {list(result.keys()) if result else 'None'}")
            if result:
                versions = result.get('versions', [])
                print(f"[DEBUG] Number of versions in response: {len(versions)}")
                if versions:
                    first_version = versions[0]
                    print(f"[DEBUG] First version keys: {list(first_version.keys())}")
                    text_data = first_version.get('text', [])
                    print(f"[DEBUG] Text type: {type(text_data)}")
                    if isinstance(text_data, list):
                        print(f"[DEBUG] Number of text segments: {len(text_data)}")
                        for idx, seg in enumerate(text_data[:5]):
                            print(f"[DEBUG] Segment {idx+1} preview: {str(seg)[:100]}...")
                    elif isinstance(text_data, str):
                        print(f"[DEBUG] Text is string, length: {len(text_data)}")
                print(f"[DEBUG] Full response ref: {result.get('ref')}")
                print(f"[DEBUG] Full response heRef: {result.get('heRef')}")
                print(f"[DEBUG] Full response he_ref: {result.get('he_ref')}")
                print(f"[DEBUG] All response keys: {list(result.keys())}")
                print(f"[DEBUG] Next ref: {result.get('next')}")
        
        return result

    def get_all_titles(self) -> List[str]:
        """
        Fetch all index titles from Sefaria.
        Endpoint: /api/index/titles
        """
        response = self._get("/index/titles")
        return response.get("books", [])

    def get_table_of_contents(self) -> List[Dict[str, Any]]:
        """
        Fetch the complete table of contents with all books and categories.
        This is more efficient than fetching each index individually.
        Endpoint: /api/index
        """
        return self._get("/index")
