import requests
from typing import Dict, Any, Optional
from .nodes import NodeFactory

class Client:
    """
    Client for the TalmudPedia SDK.
    Handles authentication and dynamic loading of the operator catalog.
    """
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        tenant_id: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.tenant_id = tenant_id
        self.headers = {}
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"
        if self.tenant_id:
            self.headers["X-Tenant-ID"] = self.tenant_id
        if extra_headers:
            self.headers.update(extra_headers)
        
        # Default tenant header if running in single-tenant dev mode or similar
        # Ideally this is passed in init, but for now we assume default/admin access
            
        self._nodes = None
        self._agent_nodes = None
        
    @property
    def nodes(self) -> NodeFactory:
        """Access RAG nodes dynamically."""
        if not self._nodes:
            self.connect()
        return self._nodes

    @property
    def agent_nodes(self) -> NodeFactory:
        """Access Agent nodes dynamically."""
        if not self._agent_nodes:
            self.connect()
        return self._agent_nodes

    def connect(self):
        """Fetch catalogs and build node factories."""
        # 1. Fetch RAG Catalog
        try:
            # Prefix from main.py: /admin/pipelines
            rag_resp = requests.get(f"{self.base_url}/admin/pipelines/catalog", headers=self.headers)
            rag_resp.raise_for_status()
            rag_catalog = rag_resp.json()
        except Exception as e:
            print(f"Warning: Failed to fetch RAG catalog: {e}")
            rag_catalog = {}

        # 2. Fetch Agent Catalog
        try:
            # Prefix from main.py: /agents
            agent_resp = requests.get(f"{self.base_url}/agents/operators", headers=self.headers)
            agent_resp.raise_for_status()
            agent_catalog = agent_resp.json()
        except Exception as e:
            print(f"Warning: Failed to fetch Agent catalog: {e}")
            agent_catalog = []

        # 3. Initialize Node Factories
        self._nodes = NodeFactory(rag_catalog, mode="rag")
        self._agent_nodes = NodeFactory(agent_catalog, mode="agent")
        
        print(f"Connected to {self.base_url}")
        print(f"Loaded RAG operators")
        print(f"Loaded Agent operators")
