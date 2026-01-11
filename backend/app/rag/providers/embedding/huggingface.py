import os
import asyncio
from typing import List, Optional

from app.rag.interfaces.embedding import EmbeddingProvider, EmbeddingResult


class HuggingFaceEmbeddingProvider(EmbeddingProvider):
    
    MODELS = {
        "sentence-transformers/all-MiniLM-L6-v2": 384,
        "sentence-transformers/all-mpnet-base-v2": 768,
        "BAAI/bge-small-en-v1.5": 384,
        "BAAI/bge-base-en-v1.5": 768,
        "BAAI/bge-large-en-v1.5": 1024,
    }
    
    def __init__(
        self,
        model: str = "sentence-transformers/all-MiniLM-L6-v2",
        device: str = "cpu",
        api_key: str = None
    ):
        self._model_name = model
        self._device = device
        self._api_key = api_key or os.getenv("HUGGINGFACE_API_KEY")
        self._model: Optional[object] = None
        self._dimension = self.MODELS.get(model, 384)
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    @property
    def provider_name(self) -> str:
        return "huggingface"
    
    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name, device=self._device)
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for HuggingFace embeddings. "
                    "Install with: pip install sentence-transformers"
                )
    
    async def embed(self, text: str) -> EmbeddingResult:
        results = await self.embed_batch([text])
        return results[0] if results else EmbeddingResult(values=[], token_count=0)
    
    async def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        if not texts:
            return []
        
        def _encode():
            self._load_model()
            embeddings = self._model.encode(texts, convert_to_numpy=True)
            return embeddings.tolist()
        
        try:
            embeddings = await asyncio.to_thread(_encode)
            return [
                EmbeddingResult(values=emb, token_count=0)
                for emb in embeddings
            ]
        except Exception:
            return [EmbeddingResult(values=[], token_count=0) for _ in texts]
