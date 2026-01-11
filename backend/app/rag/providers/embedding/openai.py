import os
import asyncio
from typing import List

import openai

from app.rag.interfaces.embedding import EmbeddingProvider, EmbeddingResult


class OpenAIEmbeddingProvider(EmbeddingProvider):
    
    DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }
    
    def __init__(
        self,
        api_key: str = None,
        model: str = "text-embedding-3-small",
        dimensions: int = None
    ):
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._model = model
        self._dimensions = dimensions or self.DIMENSIONS.get(model, 1536)
        self._client = openai.AsyncOpenAI(api_key=self._api_key)
    
    @property
    def dimension(self) -> int:
        return self._dimensions
    
    @property
    def provider_name(self) -> str:
        return "openai"
    
    async def embed(self, text: str) -> EmbeddingResult:
        results = await self.embed_batch([text])
        return results[0] if results else EmbeddingResult(values=[], token_count=0)
    
    async def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        if not texts:
            return []
        
        all_results: List[EmbeddingResult] = []
        batch_size = 2048
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_results = await self._embed_batch_with_retry(batch)
            all_results.extend(batch_results)
        
        return all_results
    
    async def _embed_batch_with_retry(
        self,
        batch: List[str],
        max_retries: int = 3
    ) -> List[EmbeddingResult]:
        for attempt in range(max_retries):
            try:
                response = await self._client.embeddings.create(
                    model=self._model,
                    input=batch
                )
                
                results = []
                for item in response.data:
                    results.append(EmbeddingResult(
                        values=item.embedding,
                        token_count=response.usage.total_tokens // len(batch) if response.usage else 0
                    ))
                return results
                
            except openai.RateLimitError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return [EmbeddingResult(values=[], token_count=0) for _ in batch]
            except Exception:
                return [EmbeddingResult(values=[], token_count=0) for _ in batch]
        
        return [EmbeddingResult(values=[], token_count=0) for _ in batch]
