import requests
import time
from typing import Dict, Any, Optional, List

class SefariaClient:
    BASE_URL = "https://www.sefaria.org/api"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Talmudpedia-Ingestion/1.0"
        })

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{endpoint}"
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
            # Simple retry logic could go here
            time.sleep(1)
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
        return self._get(f"/v3/texts/{tref}", params=params)
