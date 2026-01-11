import os
import json
import hashlib
import tempfile
from pathlib import Path
from typing import List, Any, AsyncIterator, Optional
import asyncio

from app.rag.interfaces.document_loader import (
    DocumentLoader,
    RawDocument,
    DocumentType,
)


class S3Loader(DocumentLoader):
    
    EXTENSION_MAP = {
        ".txt": DocumentType.TEXT,
        ".md": DocumentType.MARKDOWN,
        ".json": DocumentType.JSON,
        ".csv": DocumentType.CSV,
        ".html": DocumentType.HTML,
        ".htm": DocumentType.HTML,
        ".pdf": DocumentType.PDF,
    }
    
    def __init__(
        self,
        bucket: str = None,
        aws_access_key_id: str = None,
        aws_secret_access_key: str = None,
        region_name: str = None,
        endpoint_url: str = None
    ):
        self._bucket = bucket or os.getenv("S3_BUCKET")
        self._aws_access_key_id = aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
        self._aws_secret_access_key = aws_secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY")
        self._region_name = region_name or os.getenv("AWS_REGION", "us-east-1")
        self._endpoint_url = endpoint_url or os.getenv("S3_ENDPOINT_URL")
        self._client = None
    
    @property
    def loader_name(self) -> str:
        return "s3"
    
    @property
    def supported_types(self) -> List[DocumentType]:
        return [
            DocumentType.TEXT,
            DocumentType.MARKDOWN,
            DocumentType.JSON,
            DocumentType.CSV,
            DocumentType.HTML,
            DocumentType.PDF,
        ]
    
    def _get_client(self):
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client(
                    's3',
                    aws_access_key_id=self._aws_access_key_id,
                    aws_secret_access_key=self._aws_secret_access_key,
                    region_name=self._region_name,
                    endpoint_url=self._endpoint_url
                )
            except ImportError:
                raise ImportError("boto3 is required for S3 loading. Install with: pip install boto3")
        return self._client
    
    def _generate_doc_id(self, key: str, content: str) -> str:
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"s3_{Path(key).stem}_{content_hash}"
    
    def _get_doc_type(self, key: str) -> DocumentType:
        suffix = Path(key).suffix.lower()
        return self.EXTENSION_MAP.get(suffix, DocumentType.TEXT)
    
    async def _download_object(self, key: str) -> bytes:
        client = self._get_client()
        
        def download():
            response = client.get_object(Bucket=self._bucket, Key=key)
            return response['Body'].read()
        
        return await asyncio.to_thread(download)
    
    async def _list_objects(self, prefix: str = "") -> List[str]:
        client = self._get_client()
        
        def list_all():
            keys = []
            paginator = client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get('Contents', []):
                    keys.append(obj['Key'])
            return keys
        
        return await asyncio.to_thread(list_all)
    
    async def _parse_content(self, key: str, content: bytes) -> List[RawDocument]:
        doc_type = self._get_doc_type(key)
        text_content = content.decode('utf-8', errors='ignore')
        
        if doc_type == DocumentType.JSON:
            return self._parse_json(key, text_content)
        elif doc_type == DocumentType.CSV:
            return self._parse_csv(key, text_content)
        elif doc_type == DocumentType.PDF:
            return await self._parse_pdf(key, content)
        else:
            return [RawDocument(
                id=self._generate_doc_id(key, text_content[:500]),
                content=text_content,
                doc_type=doc_type,
                metadata={
                    "bucket": self._bucket,
                    "key": key,
                    "file_name": Path(key).name
                },
                source_path=f"s3://{self._bucket}/{key}"
            )]
    
    def _parse_json(self, key: str, content: str) -> List[RawDocument]:
        data = json.loads(content)
        documents = []
        
        if isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content") or json.dumps(item)
                    doc_id = item.get("id") or self._generate_doc_id(key, f"{i}_{text[:100]}")
                    metadata = {k: v for k, v in item.items() if k not in ["text", "content", "id"]}
                else:
                    text = str(item)
                    doc_id = self._generate_doc_id(key, f"{i}_{text[:100]}")
                    metadata = {}
                
                documents.append(RawDocument(
                    id=doc_id,
                    content=text,
                    doc_type=DocumentType.JSON,
                    metadata={"bucket": self._bucket, "key": key, "index": i, **metadata},
                    source_path=f"s3://{self._bucket}/{key}"
                ))
        elif isinstance(data, dict):
            text = data.get("text") or data.get("content") or json.dumps(data)
            doc_id = data.get("id") or self._generate_doc_id(key, text[:100])
            metadata = {k: v for k, v in data.items() if k not in ["text", "content", "id"]}
            
            documents.append(RawDocument(
                id=doc_id,
                content=text,
                doc_type=DocumentType.JSON,
                metadata={"bucket": self._bucket, "key": key, **metadata},
                source_path=f"s3://{self._bucket}/{key}"
            ))
        
        return documents
    
    def _parse_csv(self, key: str, content: str) -> List[RawDocument]:
        import csv
        import io
        
        reader = csv.DictReader(io.StringIO(content))
        documents = []
        
        for i, row in enumerate(reader):
            text = row.get("text") or row.get("content") or " ".join(str(v) for v in row.values())
            doc_id = row.get("id") or self._generate_doc_id(key, f"{i}_{text[:100]}")
            metadata = {k: v for k, v in row.items() if k not in ["text", "content", "id"]}
            
            documents.append(RawDocument(
                id=doc_id,
                content=text,
                doc_type=DocumentType.CSV,
                metadata={"bucket": self._bucket, "key": key, "row": i, **metadata},
                source_path=f"s3://{self._bucket}/{key}"
            ))
        
        return documents
    
    async def _parse_pdf(self, key: str, content: bytes) -> List[RawDocument]:
        try:
            import pypdf
            import io
            
            def extract_pdf():
                reader = pypdf.PdfReader(io.BytesIO(content))
                pages = []
                for i, page in enumerate(reader.pages):
                    text = page.extract_text() or ""
                    if text.strip():
                        pages.append((i, text))
                return pages
            
            pages = await asyncio.to_thread(extract_pdf)
            
            documents = []
            for page_num, text in pages:
                documents.append(RawDocument(
                    id=self._generate_doc_id(key, f"page_{page_num}_{text[:100]}"),
                    content=text,
                    doc_type=DocumentType.PDF,
                    metadata={
                        "bucket": self._bucket,
                        "key": key,
                        "page_number": page_num + 1,
                        "total_pages": len(pages)
                    },
                    source_path=f"s3://{self._bucket}/{key}"
                ))
            
            return documents
            
        except ImportError:
            raise ImportError("pypdf is required for PDF loading. Install with: pip install pypdf")
    
    async def load(self, source: str, **kwargs: Any) -> List[RawDocument]:
        extensions = kwargs.get("extensions", list(self.EXTENSION_MAP.keys()))
        
        keys = await self._list_objects(prefix=source)
        
        documents = []
        for key in keys:
            if any(key.lower().endswith(ext) for ext in extensions):
                try:
                    content = await self._download_object(key)
                    docs = await self._parse_content(key, content)
                    documents.extend(docs)
                except Exception:
                    continue
        
        return documents
    
    async def load_stream(self, source: str, **kwargs: Any) -> AsyncIterator[RawDocument]:
        extensions = kwargs.get("extensions", list(self.EXTENSION_MAP.keys()))
        
        keys = await self._list_objects(prefix=source)
        
        for key in keys:
            if any(key.lower().endswith(ext) for ext in extensions):
                try:
                    content = await self._download_object(key)
                    docs = await self._parse_content(key, content)
                    for doc in docs:
                        yield doc
                except Exception:
                    continue
