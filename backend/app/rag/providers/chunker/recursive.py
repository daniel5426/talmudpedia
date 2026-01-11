import re
import hashlib
from typing import List, Dict, Any, Optional

import tiktoken

from app.rag.interfaces.chunker import ChunkerStrategy, Chunk


class RecursiveChunker(ChunkerStrategy):
    
    DEFAULT_SEPARATORS = [
        "\n\n",
        "\n",
        ". ",
        "? ",
        "! ",
        "; ",
        ", ",
        " ",
        ""
    ]
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: List[str] = None,
        encoding_name: str = "cl100k_base",
        length_function: str = "tokens"
    ):
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._separators = separators or self.DEFAULT_SEPARATORS
        self._encoding = tiktoken.get_encoding(encoding_name)
        self._length_function = length_function
    
    @property
    def strategy_name(self) -> str:
        return "recursive"
    
    def count_tokens(self, text: str) -> int:
        return len(self._encoding.encode(text or ""))
    
    def _length(self, text: str) -> int:
        if self._length_function == "tokens":
            return self.count_tokens(text)
        return len(text)
    
    def _generate_chunk_id(self, doc_id: str, chunk_index: int, text: str) -> str:
        content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        return f"{doc_id}__chunk_{chunk_index}__{content_hash}"
    
    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        if not separators:
            return [text]
        
        separator = separators[0]
        remaining_separators = separators[1:]
        
        if separator == "":
            return list(text)
        
        splits = text.split(separator)
        
        final_chunks = []
        good_splits = []
        
        for split in splits:
            if self._length(split) < self._chunk_size:
                good_splits.append(split)
            else:
                if good_splits:
                    merged = self._merge_splits(good_splits, separator)
                    final_chunks.extend(merged)
                    good_splits = []
                
                if remaining_separators:
                    sub_splits = self._split_text(split, remaining_separators)
                    final_chunks.extend(sub_splits)
                else:
                    final_chunks.append(split)
        
        if good_splits:
            merged = self._merge_splits(good_splits, separator)
            final_chunks.extend(merged)
        
        return final_chunks
    
    def _merge_splits(self, splits: List[str], separator: str) -> List[str]:
        merged_chunks = []
        current_chunk: List[str] = []
        current_length = 0
        
        for split in splits:
            split_length = self._length(split)
            
            if current_length + split_length + (len(separator) if current_chunk else 0) > self._chunk_size:
                if current_chunk:
                    merged_chunks.append(separator.join(current_chunk))
                    
                    overlap_chunks = []
                    overlap_length = 0
                    for prev_split in reversed(current_chunk):
                        prev_len = self._length(prev_split)
                        if overlap_length + prev_len <= self._chunk_overlap:
                            overlap_chunks.insert(0, prev_split)
                            overlap_length += prev_len + len(separator)
                        else:
                            break
                    
                    current_chunk = overlap_chunks
                    current_length = overlap_length
            
            current_chunk.append(split)
            current_length += split_length + len(separator)
        
        if current_chunk:
            merged_chunks.append(separator.join(current_chunk))
        
        return merged_chunks
    
    def chunk(
        self,
        text: str,
        doc_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        if not text or not text.strip():
            return []
        
        metadata = metadata or {}
        text = text.strip()
        
        split_texts = self._split_text(text, self._separators)
        
        chunks = []
        char_position = 0
        
        for i, chunk_text in enumerate(split_texts):
            if not chunk_text.strip():
                continue
            
            start_idx = text.find(chunk_text, char_position)
            if start_idx == -1:
                start_idx = char_position
            
            end_idx = start_idx + len(chunk_text)
            
            chunks.append(Chunk(
                id=self._generate_chunk_id(doc_id, i, chunk_text),
                text=chunk_text.strip(),
                metadata=metadata.copy(),
                start_index=start_idx,
                end_index=end_idx,
                token_count=self.count_tokens(chunk_text)
            ))
            
            char_position = end_idx
        
        return chunks
