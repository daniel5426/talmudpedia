import argparse
from pathlib import Path
from dotenv import load_dotenv
from sefaria_client import SefariaClient
from chunker import Chunker
from vector_store import VectorStore
from typing import Optional

load_dotenv(Path(__file__).parent.parent / ".env")


class TextIngester:
    def __init__(self):
        self.sefaria = SefariaClient()
        self.chunker = Chunker()
        self.vector_store = VectorStore()
    
    def detect_starting_reference(self, index_title: str, index_meta: dict) -> Optional[str]:
        categories = index_meta.get("categories", [])
        primary_category = categories[0] if categories else ""
        
        if "Talmud" in categories or "Bavli" in primary_category:
            return f"{index_title} 2a"
        elif "Mishnah" in categories:
            return f"{index_title} 1:1"
        elif any(cat in categories for cat in ["Halakhah", "Halakha"]):
            return f"{index_title} 1:1"
        elif "Tanakh" in categories or "Torah" in categories:
            return f"{index_title} 1:1"
        else:
            return f"{index_title} 1:1"
    
    def ingest_index(self, index_title: str, limit: int = 999999):
        print(f"Starting ingestion for index: {index_title}")
        
        index_meta = self.sefaria.get_index(index_title)
        if not index_meta:
            print(f"Could not find index: {index_title}")
            return
        
        current_ref = self.detect_starting_reference(index_title, index_meta)
        if not current_ref:
            print(f"Could not determine starting reference for: {index_title}")
            return
        
        print(f"Detected starting reference: {current_ref}")
        count = 0
        
        while count < limit and current_ref:
            print(f"Processing {current_ref}...")
            
            text_data = self.sefaria.get_text(current_ref)
            if not text_data:
                break
            
            texts = text_data.get('versions', [{}])[0].get('text', [])
            if isinstance(texts, str):
                texts = [texts]
            
            section_ref = text_data.get("ref")
            section_segments = []
            section_links = []
            
            for i, segment_text in enumerate(texts):
                if count >= limit:
                    break
                segment_ref = f"{section_ref}:{i+1}"
                links = self.sefaria.get_related(segment_ref)
                segment_data_payload = {
                    "ref": segment_ref,
                    "text": segment_text,
                    "index_title": index_title,
                    "version": {"versionTitle": text_data.get("versionTitle", "primary")},
                    "shape_path": [index_title, section_ref]
                }
                section_segments.append(segment_data_payload)
                section_links.append(links.get("links", []) if links else [])
                count += 1

            if section_segments:
                chunks = self.chunker.chunk_segments(section_segments, section_links)
                if chunks:
                    self.vector_store.upsert_chunks(chunks)

            if count >= limit:
                break

            current_ref = text_data.get("next")

        print(f"Ingestion complete. Processed {count} segments.")


def main():
    parser = argparse.ArgumentParser(description="Ingest Sefaria texts into vector database.")
    parser.add_argument("--index", type=str, default="Taanit", help="Sefaria Index Title to ingest")
    parser.add_argument("--limit", type=int, default=999999, help="Limit number of segments to process")
    args = parser.parse_args()
    
    ingester = TextIngester()
    ingester.ingest_index(args.index, args.limit)


if __name__ == "__main__":
    main()
