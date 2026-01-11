import os
import asyncio
import random
from typing import List

from google import genai
from google.genai import types

from app.rag.interfaces.embedding import EmbeddingProvider, EmbeddingResult


class GeminiEmbeddingProvider(EmbeddingProvider):
    
    def __init__(
        self,
        api_key: str = None,
        model: str = "gemini-embedding-001",
        task_type: str = "QUESTION_ANSWERING"
    ):
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self._model = model
        self._task_type = task_type
        self._client = genai.Client(api_key=self._api_key)
        self._dimension = 768
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    @property
    def provider_name(self) -> str:
        return "gemini"
    
    async def embed(self, text: str) -> EmbeddingResult:
        results = await self.embed_batch([text])
        return results[0] if results else EmbeddingResult(values=[], token_count=0)
    
    async def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        if not texts:
            return []
        
        all_results: List[EmbeddingResult] = []
        batch_size = 100
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_results = await self._embed_batch_with_retry(batch)
            all_results.extend(batch_results)
        
        return all_results
    
    async def _embed_batch_with_retry(
        self,
        batch: List[str],
        max_retries: int = 30,
        initial_backoff: float = 1.0
    ) -> List[EmbeddingResult]:
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                result = await asyncio.to_thread(
                    self._client.models.embed_content,
                    model=self._model,
                    contents=batch,
                    config=types.EmbedContentConfig(task_type=self._task_type)
                )
                return [
                    EmbeddingResult(values=emb.values, token_count=0)
                    for emb in result.embeddings
                ]
            
            except Exception as e:
                last_exception = e
                error_str = str(e).lower()
                
                is_rate_limit = any(x in error_str for x in [
                    "429", "rate limit", "quota", "resource exhausted"
                ])
                is_timeout = any(x in error_str for x in [
                    "timeout", "timed out", "deadline exceeded"
                ])
                is_retryable = is_rate_limit or is_timeout
                
                if not is_retryable or attempt == max_retries - 1:
                    if attempt == max_retries - 1:
                        return [EmbeddingResult(values=[], token_count=0) for _ in batch]
                    if not is_retryable:
                        return [EmbeddingResult(values=[], token_count=0) for _ in batch]
                
                backoff_time = initial_backoff * (2 ** attempt) + random.uniform(0, 1)
                if is_rate_limit:
                    backoff_time = min(backoff_time, 60.0)
                elif is_timeout:
                    backoff_time = min(backoff_time, 30.0)
                
                await asyncio.sleep(backoff_time)
        
        return [EmbeddingResult(values=[], token_count=0) for _ in batch]
