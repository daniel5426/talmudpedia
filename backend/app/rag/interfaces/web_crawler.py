from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from pydantic import BaseModel

from app.rag.interfaces.document_loader import RawDocument


class WebCrawlerRequest(BaseModel):
    start_urls: List[str]
    max_depth: Optional[int] = None
    max_pages: Optional[int] = None
    respect_robots_txt: Optional[bool] = None
    content_preference: str = "fit_markdown"
    wait_until: Optional[str] = None
    page_timeout_ms: Optional[int] = None
    scan_full_page: Optional[bool] = None


class WebCrawlerProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    async def crawl(self, request: WebCrawlerRequest) -> List[RawDocument]:
        pass
