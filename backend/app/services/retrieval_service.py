"""
Retrieval Service - Centralized retrieval abstraction.

This service provides a unified interface for querying Knowledge Stores,
abstracting away the underlying vector database implementation and
applying retrieval policies.
"""
from typing import List, Dict, Any, Optional
from uuid import UUID
from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.postgres.models import KnowledgeStore, RetrievalPolicy
from app.rag.adapters import create_adapter, SearchResult, VectorBackendAdapter
from app.services.model_resolver import ModelResolver
from app.services.credentials_service import CredentialsService


class RetrievalResult(BaseModel):
    """A result from the retrieval service."""
    id: str
    score: float
    text: str
    metadata: Dict[str, Any] = {}
    knowledge_store_id: UUID


class RetrievalService:
    """
    Centralized service for retrieving documents from Knowledge Stores.
    
    This service:
    1. Resolves the KnowledgeStore by ID
    2. Instantiates the correct vector backend adapter
    3. Resolves the embedding model from the store's configuration
    4. Embeds the query
    5. Executes the search
    6. Applies retrieval policies (reranking, hybrid search, etc.)
    """
    
    def __init__(self, db: AsyncSession):
        self._db = db
        self._adapter_cache: Dict[UUID, VectorBackendAdapter] = {}
    
    async def get_store(self, store_id: UUID) -> Optional[KnowledgeStore]:
        """Fetch a knowledge store by ID."""
        return await self._db.get(KnowledgeStore, store_id)
    
    async def _get_adapter(self, store: KnowledgeStore) -> VectorBackendAdapter:
        """Get or create an adapter for the knowledge store."""
        if store.id not in self._adapter_cache:
            config = await self._resolve_backend_config(store)
            self._adapter_cache[store.id] = create_adapter(store.backend, config)
        return self._adapter_cache[store.id]

    async def _resolve_backend_config(self, store: KnowledgeStore) -> Dict[str, Any]:
        """Merge backend config with credentials (if provided)."""
        base_config = store.backend_config or {}
        if not store.credentials_ref:
            return dict(base_config)

        credentials_service = CredentialsService(self._db, store.tenant_id)
        return await credentials_service.resolve_backend_config(base_config, store.credentials_ref)

    @staticmethod
    def _resolve_namespace(store: KnowledgeStore, namespace: Optional[str]) -> Optional[str]:
        if namespace is not None:
            return namespace
        config = store.backend_config or {}
        return config.get("namespace")
    
    async def _embed_query(self, query: str, embedding_model_id: str, tenant_id: UUID) -> List[float]:
        """Embed a query string using the store's configured embedding model."""
        resolver = ModelResolver(self._db, tenant_id)
        embedder = await resolver.resolve_embedding(
            model_id=embedding_model_id
        )
        result = await embedder.embed(query)
        return result.values
    
    async def query(
        self,
        store_id: UUID,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        policy_override: Optional[RetrievalPolicy] = None,
        namespace: Optional[str] = None
    ) -> List[RetrievalResult]:
        """
        Query a Knowledge Store for relevant documents.
        
        Args:
            store_id: The ID of the Knowledge Store to query
            query: The search query string
            top_k: Maximum number of results to return
            filters: Optional metadata filters
            policy_override: Override the store's default retrieval policy
            namespace: Optional namespace within the store
            
        Returns:
            List of RetrievalResult objects
        """
        # 1. Fetch the knowledge store
        store = await self.get_store(store_id)
        if not store:
            raise ValueError(f"Knowledge store not found: {store_id}")
        
        # 2. Get the vector backend adapter
        adapter = await self._get_adapter(store)
        
        # 3. Embed the query
        query_vector = await self._embed_query(query, store.embedding_model_id, store.tenant_id)
        
        # 4. Determine retrieval policy
        policy = policy_override or store.retrieval_policy
        effective_namespace = self._resolve_namespace(store, namespace)
        
        # 5. Execute search based on policy
        if policy == RetrievalPolicy.SEMANTIC_ONLY:
            results = await self._semantic_search(adapter, query_vector, top_k, filters, effective_namespace)
        elif policy == RetrievalPolicy.HYBRID:
            results = await self._hybrid_search(adapter, query, query_vector, top_k, filters, effective_namespace)
        elif policy == RetrievalPolicy.KEYWORD_ONLY:
            results = await self._keyword_search(adapter, query, top_k, filters, effective_namespace)
        elif policy == RetrievalPolicy.RECENCY_BOOSTED:
            results = await self._recency_boosted_search(adapter, query_vector, top_k, filters, effective_namespace)
        else:
            results = await self._semantic_search(adapter, query_vector, top_k, filters, effective_namespace)
        
        # 6. Transform to RetrievalResults
        return [
            RetrievalResult(
                id=r.id,
                score=r.score,
                text=r.text,
                metadata=r.metadata,
                knowledge_store_id=store.id
            )
            for r in results
        ]
    
    async def _semantic_search(
        self,
        adapter: VectorBackendAdapter,
        query_vector: List[float],
        top_k: int,
        filters: Optional[Dict],
        namespace: Optional[str]
    ) -> List[SearchResult]:
        """Pure vector similarity search."""
        return await adapter.query(query_vector, top_k, filters, namespace)
    
    async def _hybrid_search(
        self,
        adapter: VectorBackendAdapter,
        query: str,
        query_vector: List[float],
        top_k: int,
        filters: Optional[Dict],
        namespace: Optional[str]
    ) -> List[SearchResult]:
        """
        Hybrid search combining semantic and keyword search.
        
        For now, this fetches more semantic results and reranks.
        Future improvement: integrate with a proper lexical index.
        """
        # Get more results for reranking
        semantic_results = await adapter.query(query_vector, top_k * 2, filters, namespace)
        
        # Simple reranking: boost results where query terms appear in text
        query_terms = set(query.lower().split())
        
        scored_results = []
        for result in semantic_results:
            text_lower = result.text.lower()
            keyword_hits = sum(1 for term in query_terms if term in text_lower)
            # Boost score based on keyword hits
            hybrid_score = result.score + (keyword_hits * 0.05)
            scored_results.append((result, hybrid_score))
        
        # Sort by hybrid score and take top_k
        scored_results.sort(key=lambda x: x[1], reverse=True)
        
        return [
            SearchResult(
                id=r.id,
                score=hybrid_score,
                text=r.text,
                metadata=r.metadata
            )
            for r, hybrid_score in scored_results[:top_k]
        ]
    
    async def _keyword_search(
        self,
        adapter: VectorBackendAdapter,
        query: str,
        top_k: int,
        filters: Optional[Dict],
        namespace: Optional[str]
    ) -> List[SearchResult]:
        """
        Keyword-only search.
        
        Note: This requires backend support for full-text search.
        For now, we fall back to semantic search with keyword filtering.
        """
        # TODO: Implement true keyword search when backends support it
        # For now, this is a placeholder that falls back to semantic
        return []
    
    async def _recency_boosted_search(
        self,
        adapter: VectorBackendAdapter,
        query_vector: List[float],
        top_k: int,
        filters: Optional[Dict],
        namespace: Optional[str]
    ) -> List[SearchResult]:
        """
        Semantic search with recency boosting.
        
        Documents with more recent timestamps get a score boost.
        """
        semantic_results = await adapter.query(query_vector, top_k * 2, filters, namespace)
        
        # Apply recency boost based on 'timestamp' or 'created_at' metadata
        import time
        current_time = time.time()
        
        scored_results = []
        for result in semantic_results:
            timestamp = result.metadata.get("timestamp") or result.metadata.get("created_at")
            
            recency_boost = 0.0
            if timestamp:
                try:
                    if isinstance(timestamp, (int, float)):
                        age_days = (current_time - timestamp) / 86400
                    else:
                        # Try parsing ISO timestamp
                        from datetime import datetime
                        dt = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
                        age_days = (datetime.now(dt.tzinfo) - dt).days
                    
                    # Decay function: newer = higher boost
                    recency_boost = max(0, 0.1 * (1 - age_days / 365))
                except Exception:
                    pass
            
            boosted_score = result.score + recency_boost
            scored_results.append((result, boosted_score))
        
        scored_results.sort(key=lambda x: x[1], reverse=True)
        
        return [
            SearchResult(
                id=r.id,
                score=boosted_score,
                text=r.text,
                metadata=r.metadata
            )
            for r, boosted_score in scored_results[:top_k]
        ]
    
    async def query_multiple_stores(
        self,
        store_ids: List[UUID],
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[RetrievalResult]:
        """
        Query multiple Knowledge Stores and merge results.
        
        Results are merged and sorted by score.
        """
        all_results = []
        
        for store_id in store_ids:
            try:
                results = await self.query(store_id, query, top_k, filters)
                all_results.extend(results)
            except Exception as e:
                # Log error but continue with other stores
                print(f"Error querying store {store_id}: {e}")
        
        # Sort by score and return top_k
        all_results.sort(key=lambda x: x.score, reverse=True)
        return all_results[:top_k]
