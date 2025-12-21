import argparse
import json
import threading
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from dotenv import load_dotenv
from sefaria_client import SefariaClient
from chunker import Chunker
from vector_store import VectorStore
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from typing import Optional, Set, Dict, List, Any

load_dotenv(Path(__file__).parent.parent / ".env")


class TreeNavigator:
    def __init__(self, tree_file: Optional[Path] = None):
        self.tree_file = tree_file or Path(__file__).parent.parent / "sefaria_tree.json"
        self._tree = None
        self._ref_map: Optional[Dict[str, str]] = None
    
    def _load_tree(self) -> List[Dict]:
        if self._tree is not None:
            return self._tree
        
        if not self.tree_file.exists():
            raise FileNotFoundError(f"Tree file not found: {self.tree_file}")
        
        with open(self.tree_file, 'r') as f:
            self._tree = json.load(f)
        return self._tree
    
    def _find_node(self, tree: List[Dict], title: str) -> Optional[Dict]:
        for node in tree:
            if node.get("title") == title:
                return node
            if "children" in node:
                found = self._find_node(node.get("children", []), title)
                if found:
                    return found
        return None
    
    def _extract_books(self, node: Dict) -> List[str]:
        books = []
        if node.get("type") == "book":
            books.append(node.get("title"))
        if "children" in node:
            for child in node.get("children", []):
                books.extend(self._extract_books(child))
        return books
    
    
    def _find_all_nodes(self, tree: List[Dict], title: str) -> List[Dict]:
        nodes = []
        for node in tree:
            if node.get("title") == title:
                nodes.append(node)
            if "children" in node:
                nodes.extend(self._find_all_nodes(node.get("children", []), title))
        return nodes

    def get_books_under_title(self, title: str) -> List[str]:
        tree = self._load_tree()
        nodes = self._find_all_nodes(tree, title)
        if not nodes:
            return []
        
        all_books = []
        for node in nodes:
            all_books.extend(self._extract_books(node))
            
        return list(dict.fromkeys(all_books))  # Remove duplicates preserving order

    def _build_ref_map(self) -> Dict[str, str]:
        if self._ref_map is not None:
            return self._ref_map
        tree = self._load_tree()
        ref_map: Dict[str, str] = {}
        stack = list(tree)
        while stack:
            node = stack.pop()
            ref_val = node.get("ref")
            he_ref_val = node.get("heRef")
            if ref_val and he_ref_val and ref_val not in ref_map:
                ref_map[ref_val] = he_ref_val
            children = node.get("children", [])
            if children:
                stack.extend(children)
        self._ref_map = ref_map
        return self._ref_map

    def get_he_ref(self, ref: str) -> Optional[str]:
        ref_map = self._build_ref_map()
        return ref_map.get(ref)
    
    def _find_path_to_node(self, tree: List[Dict], target_title: str, current_path: List[str] = None) -> Optional[List[str]]:
        if current_path is None:
            current_path = []
        
        for node in tree:
            path = current_path + [node.get("title")]
            
            if node.get("title") == target_title:
                return path
            
            if "children" in node:
                found_path = self._find_path_to_node(node.get("children", []), target_title, path)
                if found_path:
                    return found_path
        
        return None
    
    def get_parent_titles(self, book_title: str) -> List[str]:
        tree = self._load_tree()
        path = self._find_path_to_node(tree, book_title)
        if not path:
            return []
        return path[:-1]
    
    def get_best_hebrew_version(self, book_title: str) -> Optional[str]:
        tree = self._load_tree()
        node = self._find_node(tree, book_title)
        if node and node.get("bestHebrewVersion"):
            return node.get("bestHebrewVersion")
        return None


_log_lock = threading.Lock()

class TextIngester:
    def __init__(self, log_file: Optional[Path] = None, error_log_file: Optional[Path] = None, tree_file: Optional[Path] = None):
        self.sefaria = SefariaClient()
        self.chunker = Chunker()
        self.lexical_chunker = Chunker(target_tokens=2000, max_tokens=3000)
        self.vector_store = VectorStore()
        self.es_client = Elasticsearch(
            os.getenv("ELASTICSEARCH_URL"),
            api_key=os.getenv("ELASTICSEARCH_API_KEY")
        )
        self.log_file = log_file or Path(__file__).parent / "ingestion_log.json"
        self.error_log_file = error_log_file or Path(__file__).parent / "ingestion_errors.json"
        self.tree_file = tree_file or Path(__file__).parent.parent / "sefaria_tree.json"
        self.tree_navigator = TreeNavigator(tree_file=self.tree_file)
        self.ingestion_log: Dict[str, Dict] = self._load_log()
        self.error_log: Dict[str, List[Dict]] = self._load_error_log()
    
    def _get_he_title(self, index_title: str, index_meta: Optional[Dict] = None) -> Optional[str]:
        """
        Get Hebrew title for a book. Tries API response first, then tree file.
        """
        if index_meta and index_meta.get("heTitle"):
            return index_meta.get("heTitle")
        
        tree = self.tree_navigator._load_tree()
        node = self.tree_navigator._find_node(tree, index_title)
        if node and node.get("heTitle"):
            return node.get("heTitle")
        
        return None
    
    def _load_log(self) -> Dict[str, Dict]:
        with _log_lock:
            if self.log_file.exists():
                try:
                    with open(self.log_file, 'r') as f:
                        return json.load(f)
                except Exception as e:
                    print(f"Warning: Could not load ingestion log: {e}")
                    return {}
            return {}
    
    def _save_log(self):
        with _log_lock:
            try:
                current_log = {}
                if self.log_file.exists():
                    try:
                        with open(self.log_file, 'r') as f:
                            current_log = json.load(f)
                    except Exception:
                        pass
                
                current_log.update(self.ingestion_log)
                
                with open(self.log_file, 'w') as f:
                    json.dump(current_log, f, indent=2)
            except Exception as e:
                print(f"Warning: Could not save ingestion log: {e}")
    
    def _reload_log(self):
        with _log_lock:
            if self.log_file.exists():
                try:
                    with open(self.log_file, 'r') as f:
                        self.ingestion_log = json.load(f)
                except Exception as e:
                    print(f"Warning: Could not reload ingestion log: {e}")
    
    def _load_error_log(self) -> Dict[str, List[Dict]]:
        with _log_lock:
            if self.error_log_file.exists():
                try:
                    with open(self.error_log_file, 'r') as f:
                        return json.load(f)
                except Exception as e:
                    print(f"Warning: Could not load error log: {e}")
                    return {}
            return {}
    
    def _save_error_log(self):
        with _log_lock:
            try:
                with open(self.error_log_file, 'w') as f:
                    json.dump(self.error_log, f, indent=2)
            except Exception as e:
                print(f"Warning: Could not save error log: {e}")
    
    def _log_error(self, index_title: str, segment_ref: str, error_type: str, error_message: str, endpoint: Optional[str] = None):
        if index_title not in self.error_log:
            self.error_log[index_title] = []
        
        error_entry = {
            "segment_ref": segment_ref,
            "error_type": error_type,
            "error_message": error_message,
            "endpoint": endpoint,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        existing = next((e for e in self.error_log[index_title] if e.get("segment_ref") == segment_ref), None)
        if existing:
            existing.update(error_entry)
        else:
            self.error_log[index_title].append(error_entry)
        
        self._save_error_log()
    
    def _get_ingested_segments(self, index_title: str) -> Set[str]:
        self._reload_log()
        if index_title not in self.ingestion_log:
            self.ingestion_log[index_title] = {"ingested_segments": []}
        return set(self.ingestion_log[index_title].get("ingested_segments", []))
    
    def _mark_segment_ingested(self, index_title: str, segment_ref: str):
        if index_title not in self.ingestion_log:
            self.ingestion_log[index_title] = {"ingested_segments": []}
        if segment_ref not in self.ingestion_log[index_title]["ingested_segments"]:
            self.ingestion_log[index_title]["ingested_segments"].append(segment_ref)
    
    def _update_last_reference(self, index_title: str, reference: str):
        if index_title not in self.ingestion_log:
            self.ingestion_log[index_title] = {"ingested_segments": []}
        self.ingestion_log[index_title]["last_reference"] = reference
    
    def _get_last_reference(self, index_title: str) -> Optional[str]:
        self._reload_log()
        if index_title in self.ingestion_log:
            return self.ingestion_log[index_title].get("last_reference")
        return None
    
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
    
    def ingest_index(self, index_title: str, limit: int = 999999, resume: bool = True, overwrite: bool = False):
        print(f"Starting ingestion for index: {index_title}")
        
        if overwrite:
            print(f"Overwrite flag is set. Resetting ingestion log for {index_title}.")
            # Reset the log for this book
            if index_title not in self.ingestion_log:
                self.ingestion_log[index_title] = {"ingested_segments": []}
            self.ingestion_log[index_title]["ingested_segments"] = []
            self.ingestion_log[index_title]["last_reference"] = None
            self._save_log()
            ingested_segments = set()
        else:
            ingested_segments = self._get_ingested_segments(index_title)

        already_ingested_count = len(ingested_segments)
        if already_ingested_count > 0:
            print(f"Found {already_ingested_count} already ingested segments. Resuming...")
        elif overwrite:
            print(f"Ready to overwrite all segments for {index_title}.")
        
        index_meta = self.sefaria.get_index(index_title)
        if not index_meta:
            print(f"Could not find index: {index_title}")
            return
        
        he_title = self._get_he_title(index_title, index_meta)
        parent_titles = self.tree_navigator.get_parent_titles(index_title)
        best_version = self.tree_navigator.get_best_hebrew_version(index_title)
        
        if best_version:
            formatted_version = f"hebrew|{best_version}"
            print(f"Using best Hebrew version: {best_version} (formatted as: {formatted_version})")
            best_version = formatted_version
        else:
            print(f"No bestHebrewVersion found in tree, using default 'primary' version")
            best_version = "primary"
        
        last_ref = self._get_last_reference(index_title) if resume else None
        if last_ref:
            print(f"Resuming from last reference: {last_ref}")
            current_ref = last_ref
        else:
            current_ref = self.detect_starting_reference(index_title, index_meta)
            if not current_ref:
                print(f"Could not determine starting reference for: {index_title}")
                return
            print(f"Detected starting reference: {current_ref}")
        
        print("Collecting all segments...")
        all_segments = []
        all_links = []
        new_segments = []
        count = 0
        skipped_count = 0
        last_processed_ref = None
        
        while count < limit and current_ref:
            print(f"Processing {current_ref}...")
            last_processed_ref = current_ref
            
            text_data = self.sefaria.get_text(current_ref, version=best_version)
            if not text_data:
                self._log_error(index_title, current_ref, "text_fetch_failed", f"Failed to fetch text for reference: {current_ref}", f"/v3/texts/{current_ref}")
                break
            
            versions = text_data.get('versions', [])
            if not versions:
                version_display = best_version.replace("hebrew|", "") if best_version.startswith("hebrew|") else best_version
                error_msg = f"Version '{version_display}' not found for reference: {current_ref}"
                print(f"ERROR: {error_msg}")
                self._log_error(index_title, current_ref, "no_versions", error_msg, f"/v3/texts/{current_ref}")
                raise ValueError(f"Version '{version_display}' not found for {index_title}. Ingestion failed.")
            
            texts = versions[0].get('text', [])
            if isinstance(texts, str):
                texts = [texts]
            
            section_ref = text_data.get("ref")
            section_he_ref = text_data.get("heRef") or text_data.get("he_ref") or self.tree_navigator.get_he_ref(section_ref)
            
            is_debug_ref = False
            if is_debug_ref:
                print(f"\n[DEBUG] Processing section: {section_ref}")
                print(f"[DEBUG] Section heRef: {section_he_ref}")
                print(f"[DEBUG] Number of text segments: {len(texts)}")
                print(f"[DEBUG] Section ref from API: {section_ref}")
            
            for i, segment_text in enumerate(texts):
                if count >= limit:
                    break
                # Avoid manufacturing refs deeper than the book supports.
                # If section_ref already has a subref (e.g., "Shulchan Arukh, Even HaEzer 1:1"),
                # treat each returned line as part of that same ref instead of appending another index.
                if len(texts) > 1:
                    segment_ref = f"{section_ref}:{i+1}"
                    segment_he_ref = f"{section_he_ref}:{i+1}" if section_he_ref else None
                else:
                    segment_ref = section_ref
                    segment_he_ref = section_he_ref
                
                if is_debug_ref:
                    print(f"[DEBUG] Processing segment {i+1}: {segment_ref}")
                    print(f"[DEBUG] Segment heRef: {segment_he_ref}")
                    print(f"[DEBUG] Segment text length: {len(segment_text) if segment_text else 0}")
                    print(f"[DEBUG] Segment text preview: {str(segment_text)[:200] if segment_text else 'None'}...")
                
                if segment_ref in ingested_segments:
                    if is_debug_ref:
                        print(f"[DEBUG] Segment {segment_ref} already ingested, skipping")
                    skipped_count += 1
                    continue
                
                cleaned_text = self.chunker.clean_text(segment_text)
                if is_debug_ref:
                    print(f"[DEBUG] After cleaning - length: {len(cleaned_text)}, text: {cleaned_text[:200] if cleaned_text else 'EMPTY'}...")
                
                if not cleaned_text:
                    if is_debug_ref:
                        print(f"[DEBUG] Segment {segment_ref} has empty text after cleaning, skipping")
                    self._log_error(index_title, segment_ref, "empty_text", f"Segment has empty text after cleaning: {segment_ref}", None)
                    continue
                
                links = self.sefaria.get_related(segment_ref)
                if not links:
                    self._log_error(index_title, segment_ref, "links_fetch_failed", f"Failed to fetch links for segment: {segment_ref}", f"/related/{segment_ref}")
                    links = {}
                
                segment_data_payload = {
                    "ref": segment_ref,
                    "he_ref": segment_he_ref,
                    "text": segment_text,
                    "index_title": index_title,
                    "he_title": he_title,
                    "version": {"versionTitle": text_data.get("versionTitle", "primary")},
                    "shape_path": [index_title, section_ref],
                    "parent_titles": parent_titles
                }
                all_segments.append(segment_data_payload)
                all_links.append(links.get("links", []) if links else [])
                new_segments.append(segment_ref)
                
                if is_debug_ref:
                    print(f"[DEBUG] Added segment {segment_ref} to all_segments (total: {len(all_segments)})")
                
                count += 1

            if count >= limit:
                break

            current_ref = text_data.get("next")
        
        if not all_segments:
            print("No new segments to process.")
            return
        
        debug_segment_refs = [seg.get("ref") for seg in all_segments if "Even HaEzer.23" in seg.get("ref", "") or "Even_HaEzer.23" in seg.get("ref", "")]
        if debug_segment_refs:
            print(f"\n[DEBUG] Found {len(debug_segment_refs)} debug segments in all_segments: {debug_segment_refs}")
        
        print(f"Collected {len(all_segments)} segments. Starting chunking in batches of 100...")
        all_chunks = []
        batch_size = 100
        
        for i in range(0, len(all_segments), batch_size):
            batch_segments = all_segments[i:i + batch_size]
            batch_links = all_links[i:i + batch_size]
            batch_debug_segments = [seg.get("ref") for seg in batch_segments if "Even HaEzer.23" in seg.get("ref", "") or "Even_HaEzer.23" in seg.get("ref", "")]
            if batch_debug_segments:
                print(f"[DEBUG] Chunking batch {i // batch_size + 1} contains debug segments: {batch_debug_segments}")
            print(f"Chunking batch {i // batch_size + 1} ({len(batch_segments)} segments)...")
            chunks = self.chunker.chunk_segments(batch_segments, batch_links)
            debug_chunks = [chunk for chunk in chunks if any(ref in chunk.get("metadata", {}).get("segment_refs", []) for ref in debug_segment_refs)]
            if debug_chunks:
                print(f"[DEBUG] Created {len(debug_chunks)} chunks for debug segments in this batch")
                for chunk in debug_chunks:
                    print(f"[DEBUG] Chunk ID: {chunk.get('id')}, segment_refs: {chunk.get('metadata', {}).get('segment_refs', [])}")
            all_chunks.extend(chunks)
        
        print(f"Created {len(all_chunks)} chunks. Upserting to vector store in batches...")
        if all_chunks:
            upsert_batch_size = 50
            total_upserted = 0
            all_ingested_segments = set()
            
            for i in range(0, len(all_chunks), upsert_batch_size):
                batch_chunks = all_chunks[i:i + upsert_batch_size]
                batch_segment_refs = set()
                
                for chunk in batch_chunks:
                    segment_refs = chunk.get("metadata", {}).get("segment_refs", [])
                    if segment_refs:
                        batch_segment_refs.update(segment_refs)
                
                batch_debug_chunks = [chunk for chunk in batch_chunks if any(ref in chunk.get("metadata", {}).get("segment_refs", []) for ref in debug_segment_refs)]
                if batch_debug_chunks:
                    print(f"[DEBUG] Upserting batch {i // upsert_batch_size + 1} contains {len(batch_debug_chunks)} debug chunks")
                    for chunk in batch_debug_chunks:
                        print(f"[DEBUG] Upserting chunk ID: {chunk.get('id')}, segment_refs: {chunk.get('metadata', {}).get('segment_refs', [])}")
                
                print(f"Upserting batch {i // upsert_batch_size + 1} ({len(batch_chunks)} chunks)...")
                try:
                    self.vector_store.upsert_chunks(batch_chunks)
                    for segment_ref in batch_segment_refs:
                        self._mark_segment_ingested(index_title, segment_ref)
                        all_ingested_segments.add(segment_ref)
                    if batch_debug_chunks:
                        debug_ingested = [ref for ref in batch_segment_refs if any(dref in ref for dref in debug_segment_refs)]
                        if debug_ingested:
                            print(f"[DEBUG] Marked debug segments as ingested: {debug_ingested}")
                    if last_processed_ref:
                        self._update_last_reference(index_title, last_processed_ref)
                    self._save_log()
                    total_upserted += len(batch_chunks)
                    print(f"Successfully upserted batch {i // upsert_batch_size + 1}. Marked {len(batch_segment_refs)} segments as ingested.")
                except Exception as e:
                    print(f"Error upserting batch {i // upsert_batch_size + 1}: {e}")
                    if batch_debug_chunks:
                        print(f"[DEBUG] ERROR: Failed to upsert debug chunks!")
                    print(f"Skipping marking segments as ingested for this batch.")
            
            print(f"Upserted {total_upserted} chunks successfully. Total segments marked as ingested: {len(all_ingested_segments)}")

        # --- Lexical Ingestion ---
        print(f"Starting Lexical Ingestion for {len(all_segments)} segments...")
        
        # Chunk for lexical
        print(f"Creating lexical chunks (target=2000 tokens)...")
        lexical_chunks = self.lexical_chunker.chunk_segments(all_segments, all_links)
        print(f"Created {len(lexical_chunks)} lexical chunks.")
        
        if lexical_chunks:
            # Prepare actions for bulk API
            actions = []
            for chunk in lexical_chunks:
                action = {
                    "_index": "reshet",
                    "_id": chunk["id"],
                    "_source": {
                        "text": chunk["text"],
                        **chunk["metadata"]
                    }
                }
                actions.append(action)
            
            print(f"Ingesting {len(actions)} lexical chunks into Elasticsearch...")
            try:
                success, failed = bulk(self.es_client, actions, stats_only=True)
                print(f"Lexical Ingestion Complete: {success} successful, {failed} failed.")
            except Exception as e:
                print(f"Error during lexical ingestion: {e}")
                self._log_error(index_title, "lexical_bulk", "lexical_ingestion_error", str(e), None)


        print(f"Ingestion complete. Processed {count} new segments, skipped {skipped_count} already ingested segments.")
        print(f"Total segments in log: {len(self._get_ingested_segments(index_title))}")


def process_book(book: str, log_file: Optional[Path], error_log_file: Optional[Path], tree_file: Optional[Path], limit: int, resume: bool, overwrite: bool = False) -> Dict[str, Any]:
    """
    Process a single book in a thread.
    Returns a result dictionary with book name and status.
    """
    ingester = TextIngester(log_file=log_file, error_log_file=error_log_file, tree_file=tree_file)
    try:
        print(f"[{threading.current_thread().name}] Starting ingestion for: {book}")
        ingester.ingest_index(book, limit, resume=resume, overwrite=overwrite)
        print(f"[{threading.current_thread().name}] Completed ingestion for: {book}")
        return {"book": book, "status": "success"}
    except Exception as e:
        print(f"[{threading.current_thread().name}] Error processing book {book}: {e}")
        ingester._log_error(book, "N/A", "book_processing_error", str(e), None)
        return {"book": book, "status": "error", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Ingest Sefaria texts into vector database.")
    parser.add_argument("--titles", nargs='+', default=["Shulchan Arukh, Orach Chayim"], help="Category or book titles from tree to ingest (space-separated). All books under these titles will be ingested.")
    parser.add_argument("--limit", type=int, default=999999, help="Limit number of segments to process per index")
    parser.add_argument("--no-resume", action="store_true", help="Don't resume from previous ingestion, start from beginning")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite already ingested segments in the log and vector store")
    parser.add_argument("--log-file", type=str, default=None, help="Path to ingestion log file (default: ingestion_log.json)")
    parser.add_argument("--error-log-file", type=str, default=None, help="Path to error log file (default: ingestion_errors.json)")
    parser.add_argument("--tree-file", type=str, default=None, help="Path to sefaria_tree.json file (default: backend/sefaria_tree.json)")
    parser.add_argument("--max-workers", type=int, default=50, help="Maximum number of parallel threads (default: 20)")
    args = parser.parse_args()

    log_file = Path(args.log_file) if args.log_file else None
    error_log_file = Path(args.error_log_file) if args.error_log_file else None
    tree_file = Path(args.tree_file) if args.tree_file else None
    
    navigator = TreeNavigator(tree_file=tree_file)

    all_books = []
    for title in args.titles:
        books = navigator.get_books_under_title(title)
        if not books:
            print(f"⚠️  No books found under '{title}'. It might not exist in the tree or might be a book name (not a category).")
            books = [title]
        all_books.extend(books)
    
    all_books = list(set(all_books))
    
    print(f"Found {len(all_books)} unique books to ingest from {len(args.titles)} title(s).")
    print(f"Books: {', '.join(all_books[:10])}{'...' if len(all_books) > 10 else ''}")
    print(f"Processing with {args.max_workers} parallel threads...")
    if error_log_file:
        print(f"Error log will be saved to: {error_log_file}")

    results = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_book = {
            executor.submit(process_book, book, log_file, error_log_file, tree_file, args.limit, not args.no_resume, args.overwrite): book 
            for book in all_books
        }
        
        for future in as_completed(future_to_book):
            book = future_to_book[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                print(f"Exception for book {book}: {e}")
                results.append({"book": book, "status": "error", "error": str(e)})

    successful = sum(1 for r in results if r.get("status") == "success")
    failed = len(results) - successful
    
    print(f"\n{'='*50}")
    print(f"All books processed.")
    print(f"Successful: {successful}, Failed: {failed}")
    print(f"{'='*50}")
    
    if failed > 0:
        print("\nFailed books:")
        for result in results:
            if result.get("status") == "error":
                print(f"  - {result['book']}: {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    main()
