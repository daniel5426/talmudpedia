from typing import Optional, Dict, Any
from enum import Enum

from pydantic import BaseModel

from app.rag.interfaces import (
    EmbeddingProvider,
    VectorStoreProvider,
    ChunkerStrategy,
    DocumentLoader,
)
from app.rag.providers.embedding.gemini import GeminiEmbeddingProvider
from app.rag.providers.embedding.openai import OpenAIEmbeddingProvider
from app.rag.providers.embedding.huggingface import HuggingFaceEmbeddingProvider
from app.rag.providers.vector_store.pinecone import PineconeVectorStore
from app.rag.providers.vector_store.pgvector import PgvectorVectorStore
from app.rag.providers.vector_store.qdrant import QdrantVectorStore
from app.rag.providers.chunker.token_based import TokenBasedChunker
from app.rag.providers.chunker.recursive import RecursiveChunker
from app.rag.providers.loader.local_file import LocalFileLoader
from app.rag.providers.loader.s3 import S3Loader


class EmbeddingProviderType(str, Enum):
    GEMINI = "gemini"
    OPENAI = "openai"
    HUGGINGFACE = "huggingface"


class VectorStoreType(str, Enum):
    PINECONE = "pinecone"
    PGVECTOR = "pgvector"
    QDRANT = "qdrant"


class ChunkerType(str, Enum):
    TOKEN_BASED = "token_based"
    RECURSIVE = "recursive"


class LoaderType(str, Enum):
    LOCAL = "local"
    S3 = "s3"


class EmbeddingConfig(BaseModel):
    provider: EmbeddingProviderType = EmbeddingProviderType.GEMINI
    api_key: Optional[str] = None
    model: Optional[str] = None
    extra: Dict[str, Any] = {}


class VectorStoreConfig(BaseModel):
    provider: VectorStoreType = VectorStoreType.PINECONE
    api_key: Optional[str] = None
    connection_string: Optional[str] = None
    url: Optional[str] = None
    environment: Optional[str] = None
    cloud: str = "aws"
    region: str = "us-east-1"
    extra: Dict[str, Any] = {}


class ChunkerConfig(BaseModel):
    strategy: ChunkerType = ChunkerType.TOKEN_BASED
    chunk_size: int = 650
    max_tokens: int = 750
    overlap_tokens: int = 50
    target_tokens: int = 650
    extra: Dict[str, Any] = {}


class LoaderConfig(BaseModel):
    loader_type: LoaderType = LoaderType.LOCAL
    base_path: Optional[str] = None
    bucket: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    region_name: Optional[str] = None
    endpoint_url: Optional[str] = None
    extra: Dict[str, Any] = {}


class RAGConfig(BaseModel):
    embedding: EmbeddingConfig = EmbeddingConfig()
    vector_store: VectorStoreConfig = VectorStoreConfig()
    chunker: ChunkerConfig = ChunkerConfig()
    loader: LoaderConfig = LoaderConfig()


class RAGFactory:
    
    _embedding_cache: Dict[str, EmbeddingProvider] = {}
    _vector_store_cache: Dict[str, VectorStoreProvider] = {}
    
    @classmethod
    def create_embedding_provider(
        cls,
        config: EmbeddingConfig,
        use_cache: bool = True
    ) -> EmbeddingProvider:
        cache_key = f"{config.provider}_{config.model or 'default'}"
        
        if use_cache and cache_key in cls._embedding_cache:
            return cls._embedding_cache[cache_key]
        
        provider: EmbeddingProvider
        
        if config.provider == EmbeddingProviderType.GEMINI:
            provider = GeminiEmbeddingProvider(
                api_key=config.api_key,
                model=config.model or "gemini-embedding-001",
                **config.extra
            )
        elif config.provider == EmbeddingProviderType.OPENAI:
            provider = OpenAIEmbeddingProvider(
                api_key=config.api_key,
                model=config.model or "text-embedding-3-small",
                **config.extra
            )
        elif config.provider == EmbeddingProviderType.HUGGINGFACE:
            provider = HuggingFaceEmbeddingProvider(
                model=config.model or "sentence-transformers/all-MiniLM-L6-v2",
                **config.extra
            )
        else:
            raise ValueError(f"Unknown embedding provider: {config.provider}")
        
        if use_cache:
            cls._embedding_cache[cache_key] = provider
        
        return provider
    
    @classmethod
    def create_vector_store(
        cls,
        config: VectorStoreConfig,
        use_cache: bool = True
    ) -> VectorStoreProvider:
        cache_key = f"{config.provider}_{config.environment or config.url or 'default'}"
        
        if use_cache and cache_key in cls._vector_store_cache:
            return cls._vector_store_cache[cache_key]
        
        provider: VectorStoreProvider
        
        if config.provider == VectorStoreType.PINECONE:
            provider = PineconeVectorStore(
                api_key=config.api_key,
                environment=config.environment,
                cloud=config.cloud,
                region=config.region
            )
        elif config.provider == VectorStoreType.PGVECTOR:
            provider = PgvectorVectorStore(
                connection_string=config.connection_string,
                **config.extra
            )
        elif config.provider == VectorStoreType.QDRANT:
            provider = QdrantVectorStore(
                url=config.url,
                api_key=config.api_key,
                **config.extra
            )
        else:
            raise ValueError(f"Unknown vector store provider: {config.provider}")
        
        if use_cache:
            cls._vector_store_cache[cache_key] = provider
        
        return provider
    
    @classmethod
    def create_chunker(cls, config: ChunkerConfig) -> ChunkerStrategy:
        if config.strategy == ChunkerType.TOKEN_BASED:
            return TokenBasedChunker(
                target_tokens=config.target_tokens,
                max_tokens=config.max_tokens,
                overlap_tokens=config.overlap_tokens
            )
        elif config.strategy == ChunkerType.RECURSIVE:
            return RecursiveChunker(
                chunk_size=config.chunk_size,
                chunk_overlap=config.overlap_tokens,
                **config.extra
            )
        else:
            raise ValueError(f"Unknown chunker strategy: {config.strategy}")
    
    @classmethod
    def create_loader(cls, config: LoaderConfig) -> DocumentLoader:
        if config.loader_type == LoaderType.LOCAL:
            return LocalFileLoader(
                base_path=config.base_path
            )
        elif config.loader_type == LoaderType.S3:
            return S3Loader(
                bucket=config.bucket,
                aws_access_key_id=config.aws_access_key_id,
                aws_secret_access_key=config.aws_secret_access_key,
                region_name=config.region_name,
                endpoint_url=config.endpoint_url
            )
        else:
            raise ValueError(f"Unknown loader type: {config.loader_type}")
    
    @classmethod
    def create_from_config(cls, config: RAGConfig) -> tuple[
        EmbeddingProvider,
        VectorStoreProvider,
        ChunkerStrategy,
        DocumentLoader
    ]:
        embedding = cls.create_embedding_provider(config.embedding)
        vector_store = cls.create_vector_store(config.vector_store)
        chunker = cls.create_chunker(config.chunker)
        loader = cls.create_loader(config.loader)
        
        return embedding, vector_store, chunker, loader
    
    @classmethod
    def get_available_providers(cls) -> Dict[str, list]:
        return {
            "embedding": [e.value for e in EmbeddingProviderType],
            "vector_store": [v.value for v in VectorStoreType],
            "chunker": [c.value for c in ChunkerType],
            "loader": [l.value for l in LoaderType],
        }
