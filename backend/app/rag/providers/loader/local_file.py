import os
import json
import hashlib
from pathlib import Path
from typing import List, Any, AsyncIterator
import asyncio
import aiofiles

from app.rag.interfaces.document_loader import (
    DocumentLoader,
    RawDocument,
    DocumentType,
)


class LocalFileLoader(DocumentLoader):
    
    EXTENSION_MAP = {
        ".txt": DocumentType.TEXT,
        ".md": DocumentType.MARKDOWN,
        ".json": DocumentType.JSON,
        ".csv": DocumentType.CSV,
        ".html": DocumentType.HTML,
        ".htm": DocumentType.HTML,
        ".pdf": DocumentType.PDF,
    }
    
    def __init__(self, base_path: str = None):
        self._base_path = Path(base_path) if base_path else Path.cwd()
    
    @property
    def loader_name(self) -> str:
        return "local_file"
    
    @property
    def supported_types(self) -> List[DocumentType]:
        return [
            DocumentType.TEXT,
            DocumentType.MARKDOWN,
            DocumentType.JSON,
            DocumentType.CSV,
            DocumentType.HTML,
        ]
    
    def _generate_doc_id(self, path: str, content: str) -> str:
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"local_{Path(path).stem}_{content_hash}"
    
    def _get_doc_type(self, path: Path) -> DocumentType:
        return self.EXTENSION_MAP.get(path.suffix.lower(), DocumentType.TEXT)
    
    async def _read_file(self, path: Path) -> str:
        async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
            return await f.read()
    
    async def _read_json(self, path: Path) -> List[RawDocument]:
        content = await self._read_file(path)
        data = json.loads(content)
        
        documents = []
        if isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content") or json.dumps(item)
                    doc_id = item.get("id") or self._generate_doc_id(str(path), f"{i}_{text[:100]}")
                    metadata = {k: v for k, v in item.items() if k not in ["text", "content", "id"]}
                else:
                    text = str(item)
                    doc_id = self._generate_doc_id(str(path), f"{i}_{text[:100]}")
                    metadata = {}
                
                documents.append(RawDocument(
                    id=doc_id,
                    content=text,
                    doc_type=DocumentType.JSON,
                    metadata={"source_file": str(path), "index": i, **metadata},
                    source_path=str(path)
                ))
        elif isinstance(data, dict):
            text = data.get("text") or data.get("content") or json.dumps(data)
            doc_id = data.get("id") or self._generate_doc_id(str(path), text[:100])
            metadata = {k: v for k, v in data.items() if k not in ["text", "content", "id"]}
            
            documents.append(RawDocument(
                id=doc_id,
                content=text,
                doc_type=DocumentType.JSON,
                metadata={"source_file": str(path), **metadata},
                source_path=str(path)
            ))
        
        return documents
    
    async def _read_csv(self, path: Path) -> List[RawDocument]:
        import csv
        import io
        
        content = await self._read_file(path)
        reader = csv.DictReader(io.StringIO(content))
        
        documents = []
        for i, row in enumerate(reader):
            text = row.get("text") or row.get("content") or " ".join(str(v) for v in row.values())
            doc_id = row.get("id") or self._generate_doc_id(str(path), f"{i}_{text[:100]}")
            metadata = {k: v for k, v in row.items() if k not in ["text", "content", "id"]}
            
            documents.append(RawDocument(
                id=doc_id,
                content=text,
                doc_type=DocumentType.CSV,
                metadata={"source_file": str(path), "row": i, **metadata},
                source_path=str(path)
            ))
        
        return documents
    
    async def _read_text_file(self, path: Path) -> RawDocument:
        content = await self._read_file(path)
        doc_type = self._get_doc_type(path)
        
        return RawDocument(
            id=self._generate_doc_id(str(path), content[:500]),
            content=content,
            doc_type=doc_type,
            metadata={
                "source_file": str(path),
                "file_name": path.name,
                "file_size": path.stat().st_size
            },
            source_path=str(path)
        )
    
    async def load(self, source: str, **kwargs: Any) -> List[RawDocument]:
        path = self._base_path / source if not Path(source).is_absolute() else Path(source)
        
        if not path.exists():
            raise FileNotFoundError(f"Path not found: {path}")
        
        documents = []
        
        if path.is_file():
            docs = await self._load_single_file(path)
            documents.extend(docs)
        elif path.is_dir():
            recursive = kwargs.get("recursive", True)
            extensions = kwargs.get("extensions", list(self.EXTENSION_MAP.keys()))
            
            pattern = "**/*" if recursive else "*"
            for file_path in path.glob(pattern):
                if file_path.is_file() and file_path.suffix.lower() in extensions:
                    try:
                        docs = await self._load_single_file(file_path)
                        documents.extend(docs)
                    except Exception:
                        continue
        
        return documents
    
    async def _load_single_file(self, path: Path) -> List[RawDocument]:
        suffix = path.suffix.lower()
        
        if suffix == ".json":
            return await self._read_json(path)
        elif suffix == ".csv":
            return await self._read_csv(path)
        elif suffix == ".pdf":
            return await self._read_pdf(path)
        else:
            doc = await self._read_text_file(path)
            return [doc]
    
    async def _read_pdf(self, path: Path) -> List[RawDocument]:
        try:
            import pypdf
            
            def extract_pdf():
                reader = pypdf.PdfReader(str(path))
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
                    id=self._generate_doc_id(str(path), f"page_{page_num}_{text[:100]}"),
                    content=text,
                    doc_type=DocumentType.PDF,
                    metadata={
                        "source_file": str(path),
                        "page_number": page_num + 1,
                        "total_pages": len(pages)
                    },
                    source_path=str(path)
                ))
            
            return documents
            
        except ImportError:
            raise ImportError("pypdf is required for PDF loading. Install with: pip install pypdf")
    
    async def load_stream(self, source: str, **kwargs: Any) -> AsyncIterator[RawDocument]:
        path = self._base_path / source if not Path(source).is_absolute() else Path(source)
        
        if not path.exists():
            raise FileNotFoundError(f"Path not found: {path}")
        
        if path.is_file():
            docs = await self._load_single_file(path)
            for doc in docs:
                yield doc
        elif path.is_dir():
            recursive = kwargs.get("recursive", True)
            extensions = kwargs.get("extensions", list(self.EXTENSION_MAP.keys()))
            
            pattern = "**/*" if recursive else "*"
            for file_path in path.glob(pattern):
                if file_path.is_file() and file_path.suffix.lower() in extensions:
                    try:
                        docs = await self._load_single_file(file_path)
                        for doc in docs:
                            yield doc
                    except Exception:
                        continue
