from typing import List, Dict, Any, Optional
import requests

class ArtifactBuilder:
    """Helper to create Custom Artifacts via the API."""
    
    @staticmethod
    def create(
        client,
        name: str,
        python_code: str,
        category: str = "custom",
        input_type: str = "raw_documents",
        output_type: str = "normalized_documents",
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        config_schema: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new custom operator/artifact in the backend.
        This persists it to the database, making it available immediately.
        """
        payload = {
            "name": name,
            "display_name": display_name or name,
            "category": category,
            "description": description or "",
            "python_code": python_code,
            "input_type": input_type,
            "output_type": output_type,
            "config_schema": config_schema or []
        }
        
        # Endpoint from main.py: /admin/rag/custom-operators
        resp = requests.post(
            f"{client.base_url}/admin/rag/custom-operators",
            json=payload,
            headers=client.headers
        )
        resp.raise_for_status()
        
        # After creation, we should ideally refresh the client nodes
        # so the new artifact is available immediately in this session
        client.connect()
        
        return resp.json()
