from typing import List, Dict, Any, Optional
import re
import tiktoken


class Chunker:
    def __init__(self, target_tokens: int = 650, max_tokens: int = 750, encoding_name: str = "cl100k_base"):
        """Configure tokenizer and chunk size goals."""
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens
        self.encoding = tiktoken.get_encoding(encoding_name)

    def clean_text(self, text: str) -> str:
        """Remove HTML tags and normalize text."""
        if not text:
            return ""
        clean = re.sub(r'<[^>]+>', '', text)
        clean = " ".join(clean.split())
        return clean

    def count_tokens(self, text: str) -> int:
        """Count tokens for the configured encoder."""
        return len(self.encoding.encode(text or ""))

    def _combine_refs(self, refs: List[str]) -> str:
        """Build a range label from the buffered refs."""
        refs = [ref for ref in refs if ref]
        if not refs:
            return "segment"
        first = refs[0]
        last = refs[-1]
        if first == last or not last:
            return first
        return f"{first}-{last}"

    def _merge_links(self, link_groups: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Deduplicate link metadata within a chunk."""
        merged = []
        seen = set()
        for group in link_groups:
            for link in group or []:
                link_id = link.get("_id")
                if link_id and link_id in seen:
                    continue
                if link_id:
                    seen.add(link_id)
                merged.append(link)
        return merged

    def _build_chunk(self, segments: List[Dict[str, Any]], link_groups: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Create a chunk from buffered segments."""
        if not segments:
            return {}
        combined_text = " ".join(segment["text"] for segment in segments if segment["text"]).strip()
        if not combined_text:
            return {}
        base_segment = segments[0]
        segment_refs = [segment.get("ref") for segment in segments]
        segment_ref = self._combine_refs(segment_refs)
        segment_he_refs = [segment.get("he_ref") for segment in segments if segment.get("he_ref")]
        segment_he_ref = self._combine_refs(segment_he_refs) if segment_he_refs else None
        return self.create_vector_chunk(
            segment_ref=segment_ref,
            text=combined_text,
            index_title=base_segment.get("index_title"),
            he_title=base_segment.get("he_title"),
            version_title=base_segment.get("version_title"),
            links=self._merge_links(link_groups),
            shape_path=base_segment.get("shape_path", []),
            segment_refs=segment_refs,
            parent_titles=base_segment.get("parent_titles", []),
            he_ref=segment_he_ref
        )

    def create_vector_chunk(
        self,
        segment_ref: str,
        text: str,
        index_title: str,
        version_title: str,
        links: List[Dict[str, Any]],
        shape_path: List[str],
        segment_refs: List[str] = None,
        he_title: Optional[str] = None,
        parent_titles: Optional[List[str]] = None,
        he_ref: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a single vector chunk payload."""
        clean_text = self.clean_text(text)
        link_ids = [link["_id"] for link in links if "_id" in link]
        chunk_id = f"{index_title}__{segment_ref}__{version_title}".replace(" ", "_").replace(":", "_")
        metadata = {
            "index_title": index_title,
            "book_name": index_title,
            "ref": segment_ref,
            "text": clean_text,
            "version_title": version_title,
            "link_ids": link_ids,
            "shape_path": shape_path,
            "start_char": 0,
            "end_char": len(clean_text)
        }
        if he_title:
            metadata["he_title"] = he_title
        if segment_refs:
            metadata["segment_refs"] = segment_refs
        if parent_titles:
            metadata["parent_titles"] = parent_titles
        if he_ref:
            metadata["heRef"] = he_ref
        return {
            "id": chunk_id,
            "text": clean_text,
            "metadata": metadata
        }

    def chunk_segments(
        self,
        segments: List[Dict[str, Any]],
        links_batch: List[List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Merge adjacent API segments into ~650 token chunks."""
        if not segments:
            return []
        buffered_segments: List[Dict[str, Any]] = []
        buffered_links: List[List[Dict[str, Any]]] = []
        buffered_tokens = 0
        chunks: List[Dict[str, Any]] = []
        for index, segment in enumerate(segments):
            raw_text = segment.get("text", "")
            clean_text = self.clean_text(raw_text)
            if not clean_text:
                continue
            segment_tokens = self.count_tokens(clean_text)
            normalized = {
                "ref": segment.get("ref"),
                "text": clean_text,
                "index_title": segment.get("index_title"),
                "he_title": segment.get("he_title"),
                "version_title": segment.get("version", {}).get("versionTitle", "unknown"),
                "shape_path": segment.get("shape_path", []),
                "parent_titles": segment.get("parent_titles", []),
                "tokens": segment_tokens
            }
            link_group = links_batch[index] if index < len(links_batch) else []
            if segment_tokens >= self.max_tokens:
                if buffered_segments:
                    chunk = self._build_chunk(buffered_segments, buffered_links)
                    if chunk:
                        chunks.append(chunk)
                    buffered_segments = []
                    buffered_links = []
                    buffered_tokens = 0
                chunk = self._build_chunk([normalized], [link_group])
                if chunk:
                    chunks.append(chunk)
                continue
            if buffered_tokens and buffered_tokens + segment_tokens > self.max_tokens:
                chunk = self._build_chunk(buffered_segments, buffered_links)
                if chunk:
                    chunks.append(chunk)
                buffered_segments = []
                buffered_links = []
                buffered_tokens = 0
            buffered_segments.append(normalized)
            buffered_links.append(link_group)
            buffered_tokens += segment_tokens
            if buffered_tokens >= self.target_tokens:
                chunk = self._build_chunk(buffered_segments, buffered_links)
                if chunk:
                    chunks.append(chunk)
                buffered_segments = []
                buffered_links = []
                buffered_tokens = 0
        if buffered_segments:
            chunk = self._build_chunk(buffered_segments, buffered_links)
            if chunk:
                chunks.append(chunk)
        return chunks
