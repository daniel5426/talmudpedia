import os
import asyncio
import json
from typing import List, Dict, Any, Optional

from app.rag.interfaces.vector_store import (
    VectorStoreProvider,
    VectorDocument,
    VectorSearchResult,
    IndexStats,
)


class PgvectorVectorStore(VectorStoreProvider):
    
    def __init__(
        self,
        connection_string: str = None,
        table_prefix: str = "rag_vectors"
    ):
        self._connection_string = connection_string or os.getenv("PGVECTOR_CONNECTION_STRING")
        self._table_prefix = table_prefix
        self._pool = None
    
    @property
    def provider_name(self) -> str:
        return "pgvector"
    
    async def _get_pool(self):
        if self._pool is None:
            try:
                import asyncpg
                self._pool = await asyncpg.create_pool(self._connection_string)
                await self._ensure_extension()
            except ImportError:
                raise ImportError(
                    "asyncpg is required for Pgvector. Install with: pip install asyncpg"
                )
        return self._pool
    
    async def _ensure_extension(self):
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    
    def _table_name(self, index_name: str) -> str:
        return f"{self._table_prefix}_{index_name}".replace("-", "_")

    @staticmethod
    def _to_pgvector_literal(values: List[float]) -> str:
        # asyncpg doesn't auto-encode Python lists for pgvector; pass a vector literal.
        return "[" + ",".join(str(float(v)) for v in values) + "]"
    
    async def create_index(
        self,
        name: str,
        dimension: int,
        metric: str = "cosine",
        **kwargs: Any
    ) -> bool:
        try:
            pool = await self._get_pool()
            table = self._table_name(name)
            
            distance_op = {
                "cosine": "vector_cosine_ops",
                "euclidean": "vector_l2_ops",
                "inner_product": "vector_ip_ops"
            }.get(metric, "vector_cosine_ops")
            
            async with pool.acquire() as conn:
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id TEXT PRIMARY KEY,
                        embedding vector({dimension}),
                        metadata JSONB,
                        namespace TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS {table}_embedding_idx 
                    ON {table} USING ivfflat (embedding {distance_op})
                    WITH (lists = 100)
                """)
                
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS {table}_namespace_idx 
                    ON {table} (namespace)
                """)
            
            return True
        except Exception:
            return False
    
    async def delete_index(self, name: str) -> bool:
        try:
            pool = await self._get_pool()
            table = self._table_name(name)
            
            async with pool.acquire() as conn:
                await conn.execute(f"DROP TABLE IF EXISTS {table}")
            
            return True
        except Exception:
            return False
    
    async def list_indices(self) -> List[str]:
        try:
            pool = await self._get_pool()
            prefix = self._table_prefix + "_"
            
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name LIKE $1
                """, prefix + "%")
            
            return [
                row["table_name"].replace(prefix, "").replace("_", "-")
                for row in rows
            ]
        except Exception:
            return []
    
    async def get_index_stats(self, name: str) -> Optional[IndexStats]:
        try:
            pool = await self._get_pool()
            table = self._table_name(name)
            
            async with pool.acquire() as conn:
                count_row = await conn.fetchrow(f"SELECT COUNT(*) as count FROM {table}")
                total_count = count_row["count"] if count_row else 0
                
                dim_row = await conn.fetchrow(f"""
                    SELECT vector_dims(embedding) as dim 
                    FROM {table} LIMIT 1
                """)
                dimension = dim_row["dim"] if dim_row else 0
                
                ns_rows = await conn.fetch(f"""
                    SELECT namespace, COUNT(*) as count 
                    FROM {table} 
                    GROUP BY namespace
                """)
                namespaces = {row["namespace"] or "": row["count"] for row in ns_rows}
            
            return IndexStats(
                name=name,
                dimension=dimension,
                total_vector_count=total_count,
                namespaces=namespaces
            )
        except Exception:
            return None
    
    async def upsert(
        self,
        index_name: str,
        documents: List[VectorDocument],
        namespace: Optional[str] = None
    ) -> int:
        if not documents:
            return 0
        
        try:
            pool = await self._get_pool()
            table = self._table_name(index_name)
            ns = namespace or ""
            
            async with pool.acquire() as conn:
                for doc in documents:
                    vector_literal = self._to_pgvector_literal(doc.values)
                    await conn.execute(f"""
                        INSERT INTO {table} (id, embedding, metadata, namespace)
                        VALUES ($1, $2::vector, $3::jsonb, $4)
                        ON CONFLICT (id) DO UPDATE SET
                            embedding = EXCLUDED.embedding,
                            metadata = EXCLUDED.metadata,
                            namespace = EXCLUDED.namespace
                    """, doc.id, vector_literal, json.dumps(doc.metadata), ns)
            
            return len(documents)
        except Exception as e:
            raise RuntimeError(f"PGVector upsert failed for collection '{index_name}': {e}") from e
    
    async def delete(
        self,
        index_name: str,
        ids: List[str],
        namespace: Optional[str] = None
    ) -> bool:
        try:
            pool = await self._get_pool()
            table = self._table_name(index_name)
            
            async with pool.acquire() as conn:
                if namespace:
                    await conn.execute(f"""
                        DELETE FROM {table} WHERE id = ANY($1) AND namespace = $2
                    """, ids, namespace)
                else:
                    await conn.execute(f"""
                        DELETE FROM {table} WHERE id = ANY($1)
                    """, ids)
            
            return True
        except Exception:
            return False
    
    async def search(
        self,
        index_name: str,
        query_vector: List[float],
        top_k: int = 10,
        namespace: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[VectorSearchResult]:
        try:
            pool = await self._get_pool()
            table = self._table_name(index_name)
            
            query = f"""
                SELECT id, metadata, 1 - (embedding <=> $1::vector) as score
                FROM {table}
                WHERE 1=1
            """
            params = [self._to_pgvector_literal(query_vector)]
            param_idx = 2
            
            if namespace:
                query += f" AND namespace = ${param_idx}"
                params.append(namespace)
                param_idx += 1
            
            if filter:
                for key, value in filter.items():
                    if isinstance(value, dict) and "$in" in value:
                        query += f" AND metadata->>'{key}' = ANY(${param_idx})"
                        params.append(value["$in"])
                    else:
                        query += f" AND metadata->>'{key}' = ${param_idx}"
                        params.append(str(value))
                    param_idx += 1
            
            query += f" ORDER BY embedding <=> $1::vector LIMIT ${param_idx}"
            params.append(top_k)
            
            async with pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
            
            return [
                VectorSearchResult(
                    id=row["id"],
                    score=float(row["score"]),
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {}
                )
                for row in rows
            ]
        except Exception as e:
            raise RuntimeError(f"PGVector search failed for collection '{index_name}': {e}") from e
