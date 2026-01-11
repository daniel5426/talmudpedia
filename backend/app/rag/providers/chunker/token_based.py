import re
import hashlib
from typing import List, Dict, Any, Optional

import tiktoken

from app.rag.interfaces.chunker import ChunkerStrategy, Chunk


class TokenBasedChunker(ChunkerStrategy):
    
    def __init__(
        self,
        target_tokens: int = 650,
        max_tokens: int = 750,
        overlap_tokens: int = 50,
        encoding_name: str = "cl100k_base"
    ):
        self._target_tokens = target_tokens
        self._max_tokens = max_tokens
        self._overlap_tokens = overlap_tokens
        self._encoding = tiktoken.get_encoding(encoding_name)
    
    @property
    def strategy_name(self) -> str:
        return "token_based"
    
    def count_tokens(self, text: str) -> int:
        return len(self._encoding.encode(text or ""))
    
    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        clean = re.sub(r'<[^>]+>', '', text)
        clean = " ".join(clean.split())
        return clean
    
    def _generate_chunk_id(self, doc_id: str, chunk_index: int, text: str) -> str:
        content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        return f"{doc_id}__chunk_{chunk_index}__{content_hash}"
    
    def chunk(
        self,
        text: str,
        doc_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        clean_text = self._clean_text(text)
        if not clean_text:
            return []
        
        metadata = metadata or {}
        sentences = self._split_into_sentences(clean_text)
        
        chunks: List[Chunk] = []
        current_sentences: List[str] = []
        current_tokens = 0
        current_start = 0
        char_position = 0
        
        for sentence in sentences:
            sentence_tokens = self.count_tokens(sentence)
            
            if sentence_tokens >= self._max_tokens:
                if current_sentences:
                    chunk_text = " ".join(current_sentences)
                    chunks.append(Chunk(
                        id=self._generate_chunk_id(doc_id, len(chunks), chunk_text),
                        text=chunk_text,
                        metadata=metadata.copy(),
                        start_index=current_start,
                        end_index=char_position,
                        token_count=current_tokens
                    ))
                    current_sentences = []
                    current_tokens = 0
                
                chunks.append(Chunk(
                    id=self._generate_chunk_id(doc_id, len(chunks), sentence),
                    text=sentence,
                    metadata=metadata.copy(),
                    start_index=char_position,
                    end_index=char_position + len(sentence),
                    token_count=sentence_tokens
                ))
                current_start = char_position + len(sentence) + 1
                char_position += len(sentence) + 1
                continue
            
            if current_tokens + sentence_tokens > self._max_tokens and current_sentences:
                chunk_text = " ".join(current_sentences)
                chunks.append(Chunk(
                    id=self._generate_chunk_id(doc_id, len(chunks), chunk_text),
                    text=chunk_text,
                    metadata=metadata.copy(),
                    start_index=current_start,
                    end_index=char_position,
                    token_count=current_tokens
                ))
                
                overlap_sentences = self._get_overlap_sentences(current_sentences)
                current_sentences = overlap_sentences
                current_tokens = sum(self.count_tokens(s) for s in overlap_sentences)
                current_start = char_position - sum(len(s) + 1 for s in overlap_sentences)
            
            current_sentences.append(sentence)
            current_tokens += sentence_tokens
            char_position += len(sentence) + 1
            
            if current_tokens >= self._target_tokens:
                chunk_text = " ".join(current_sentences)
                chunks.append(Chunk(
                    id=self._generate_chunk_id(doc_id, len(chunks), chunk_text),
                    text=chunk_text,
                    metadata=metadata.copy(),
                    start_index=current_start,
                    end_index=char_position,
                    token_count=current_tokens
                ))
                
                overlap_sentences = self._get_overlap_sentences(current_sentences)
                current_sentences = overlap_sentences
                current_tokens = sum(self.count_tokens(s) for s in overlap_sentences)
                current_start = char_position - sum(len(s) + 1 for s in overlap_sentences)
        
        if current_sentences:
            chunk_text = " ".join(current_sentences)
            chunks.append(Chunk(
                id=self._generate_chunk_id(doc_id, len(chunks), chunk_text),
                text=chunk_text,
                metadata=metadata.copy(),
                start_index=current_start,
                end_index=char_position,
                token_count=current_tokens
            ))
        
        return chunks
    
    def _split_into_sentences(self, text: str) -> List[str]:
        sentence_endings = re.compile(r'(?<=[.!?])\s+')
        sentences = sentence_endings.split(text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _get_overlap_sentences(self, sentences: List[str]) -> List[str]:
        if not sentences or self._overlap_tokens <= 0:
            return []
        
        overlap: List[str] = []
        overlap_tokens = 0
        
        for sentence in reversed(sentences):
            tokens = self.count_tokens(sentence)
            if overlap_tokens + tokens <= self._overlap_tokens:
                overlap.insert(0, sentence)
                overlap_tokens += tokens
            else:
                break
        
        return overlap
