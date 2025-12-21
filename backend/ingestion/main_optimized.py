import argparse
import json
import asyncio
import time
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from dotenv import load_dotenv
from async_sefaria_client import AsyncSefariaClient
from chunker import Chunker
from vector_store import VectorStore
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from typing import Optional, Set, Dict, List, Any
from multiprocessing import Manager

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
    
    def get_books_under_title(self, title: str) -> List[str]:
        tree = self._load_tree()
        node = self._find_node(tree, title)
        if not node:
            return []
        return self._extract_books(node)

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


class AsyncTextIngester:
    """Async version of TextIngester for I/O-bound operations."""
    
    def __init__(
        self, 
        log_file: Optional[Path] = None, 
        error_log_file: Optional[Path] = None, 
        tree_file: Optional[Path] = None,
        shared_log: Optional[Dict] = None,
        shared_error_log: Optional[Dict] = None
    ):
        self.log_file = log_file or Path(__file__).parent / "ingestion_log.json"
        self.error_log_file = error_log_file or Path(__file__).parent / "ingestion_errors.json"
        self.tree_file = tree_file or Path(__file__).parent.parent / "sefaria_tree.json"
        self.tree_navigator = TreeNavigator(tree_file=self.tree_file)
        
        # Use shared dictionaries for multiprocessing
        self.shared_log = shared_log
        self.shared_error_log = shared_error_log
        
        # Load logs
        self.ingestion_log: Dict[str, Dict] = self._load_log()
        self.error_log: Dict[str, List[Dict]] = self._load_error_log()
    
    def _get_he_title(self, index_title: str, index_meta: Optional[Dict] = None) -> Optional[str]:
        if index_meta and index_meta.get("heTitle"):
            return index_meta.get("heTitle")
        
        tree = self.tree_navigator._load_tree()
        node = self.tree_navigator._find_node(tree, index_title)
        if node and node.get("heTitle"):
            return node.get("heTitle")
        
        return None
    
    def _load_log(self) -> Dict[str, Dict]:
        if self.shared_log is not None:
            return dict(self.shared_log)
        
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load ingestion log: {e}")
                return {}
        return {}
    
    def _save_log(self):
        try:
            # Update shared log if available
            if self.shared_log is not None:
                self.shared_log.update(self.ingestion_log)
            
            # Also save to file
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
        if self.shared_log is not None:
            self.ingestion_log.update(dict(self.shared_log))
        elif self.log_file.exists():
            try:
                with open(self.log_file, 'r') as f:
                    self.ingestion_log = json.load(f)
            except Exception as e:
                print(f"Warning: Could not reload ingestion log: {e}")
    
    def _load_error_log(self) -> Dict[str, List[Dict]]:
        if self.shared_error_log is not None:
            return dict(self.shared_error_log)
        
        if self.error_log_file.exists():
            try:
                with open(self.error_log_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load error log: {e}")
                return {}
        return {}
    
    def _save_error_log(self):
        try:
            if self.shared_error_log is not None:
                self.shared_error_log.update(self.error_log)
            
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
    
    async def ingest_index(self, index_title: str, limit: int = 999999, resume: bool = True):
        """Async version of ingest_index using AsyncSefariaClient."""
        print(f"[ASYNC] Starting ingestion for index: {index_title}")
        
        ingested_segments = self._get_ingested_segments(index_title)
        already_ingested_count = len(ingested_segments)
        if already_ingested_count > 0:
            print(f"[{index_title}] Found {already_ingested_count} already ingested segments. Resuming...")
        
        async with AsyncSefariaClient(
            max_concurrent_requests=50,
            rate_limit_per_second=10
        ) as sefaria:
            index_meta = await sefaria.get_index(index_title)
            if not index_meta:
                print(f"[{index_title}] Could not find index")
                return
            
            he_title = self._get_he_title(index_title, index_meta)
            parent_titles = self.tree_navigator.get_parent_titles(index_title)
            best_version = self.tree_navigator.get_best_hebrew_version(index_title)
            
            if best_version:
                formatted_version = f"hebrew|{best_version}"
                print(f"[{index_title}] Using best Hebrew version: {best_version}")
                best_version = formatted_version
            else:
                print(f"[{index_title}] No bestHebrewVersion found, using default 'primary'")
                best_version = "primary"
            
            last_ref = self._get_last_reference(index_title) if resume else None
            if last_ref:
                print(f"[{index_title}] Resuming from last reference: {last_ref}")
                current_ref = last_ref
            else:
                current_ref = self.detect_starting_reference(index_title, index_meta)
                if not current_ref:
                    print(f"[{index_title}] Could not determine starting reference")
                    return
                print(f"[{index_title}] Detected starting reference: {current_ref}")
            
            print(f"[{index_title}] Collecting all segments...")
            all_segments = []
            all_links = []
            count = 0
            skipped_count = 0
            last_processed_ref = None
            
            # Collect all references first
            refs_to_fetch = []
            current_check_ref = current_ref
            
            while count < limit and current_check_ref:
                # Fetch text to get next reference
                text_data = await sefaria.get_text(current_check_ref, version=best_version)
                if not text_data:
                    self._log_error(index_title, current_check_ref, "text_fetch_failed", 
                                  f"Failed to fetch text for reference: {current_check_ref}", 
                                  f"/v3/texts/{current_check_ref}")
                    break
                
                refs_to_fetch.append(current_check_ref)
                count += 1
                current_check_ref = text_data.get("next")
            
            print(f"[{index_title}] Found {len(refs_to_fetch)} references to process")
            
            # Fetch all texts and links concurrently
            print(f"[{index_title}] Fetching texts and links concurrently...")
            texts = await sefaria.fetch_multiple_texts(refs_to_fetch, version=best_version)
            links = await sefaria.fetch_multiple_related(refs_to_fetch)
            
            # Process fetched data
            for text_data, link_data in zip(texts, links):
                if not text_data:
                    continue
                
                versions = text_data.get('versions', [])
                if not versions:
                    version_display = best_version.replace("hebrew|", "") if best_version.startswith("hebrew|") else best_version
                    error_msg = f"Version '{version_display}' not found"
                    print(f"[{index_title}] ERROR: {error_msg}")
                    self._log_error(index_title, text_data.get("ref", "unknown"), "no_versions", error_msg, 
                                  f"/v3/texts/{text_data.get('ref', 'unknown')}")
                    continue
                
                texts_content = versions[0].get('text', [])
                if isinstance(texts_content, str):
                    texts_content = [texts_content]
                
                section_ref = text_data.get("ref")
                section_he_ref = text_data.get("heRef") or text_data.get("he_ref") or self.tree_navigator.get_he_ref(section_ref)
                
                for i, segment_text in enumerate(texts_content):
                    if ":" in section_ref:
                        segment_ref = section_ref
                        segment_he_ref = section_he_ref
                    else:
                        segment_ref = f"{section_ref}:{i+1}"
                        segment_he_ref = f"{section_he_ref}:{i+1}" if section_he_ref else None
                    
                    if segment_ref in ingested_segments:
                        skipped_count += 1
                        continue
                    
                    # Clean text using Chunker
                    chunker = Chunker()
                    cleaned_text = chunker.clean_text(segment_text)
                    
                    if not cleaned_text:
                        self._log_error(index_title, segment_ref, "empty_text", 
                                      f"Segment has empty text after cleaning: {segment_ref}", None)
                        continue
                    
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
                    all_links.append(link_data.get("links", []) if link_data else [])
                    last_processed_ref = segment_ref
            
            if not all_segments:
                print(f"[{index_title}] No new segments to process.")
                return
            
            print(f"[{index_title}] Collected {len(all_segments)} segments. Processing...")
            
            # Process chunks and embeddings (CPU-bound work will be done in separate process)
            # For now, we'll do it here but this could be offloaded to ProcessPoolExecutor
            chunker = Chunker()
            lexical_chunker = Chunker(target_tokens=2000, max_tokens=3000)
            
            all_chunks = []
            batch_size = 100
            
            for i in range(0, len(all_segments), batch_size):
                batch_segments = all_segments[i:i + batch_size]
                batch_links = all_links[i:i + batch_size]
                print(f"[{index_title}] Chunking batch {i // batch_size + 1} ({len(batch_segments)} segments)...")
                chunks = chunker.chunk_segments(batch_segments, batch_links)
                all_chunks.extend(chunks)
            
            print(f"[{index_title}] Created {len(all_chunks)} chunks. Upserting to vector store...")
            
            if all_chunks:
                vector_store = VectorStore()
                upsert_batch_size = 50
                total_upserted = 0
                
                for i in range(0, len(all_chunks), upsert_batch_size):
                    batch_chunks = all_chunks[i:i + upsert_batch_size]
                    batch_segment_refs = set()
                    
                    for chunk in batch_chunks:
                        segment_refs = chunk.get("metadata", {}).get("segment_refs", [])
                        if segment_refs:
                            batch_segment_refs.update(segment_refs)
                    
                    print(f"[{index_title}] Upserting batch {i // upsert_batch_size + 1} ({len(batch_chunks)} chunks)...")
                    try:
                        vector_store.upsert_chunks(batch_chunks)
                        for segment_ref in batch_segment_refs:
                            self._mark_segment_ingested(index_title, segment_ref)
                        if last_processed_ref:
                            self._update_last_reference(index_title, last_processed_ref)
                        self._save_log()
                        total_upserted += len(batch_chunks)
                        print(f"[{index_title}] Successfully upserted batch {i // upsert_batch_size + 1}")
                    except Exception as e:
                        print(f"[{index_title}] Error upserting batch: {e}")
                
                print(f"[{index_title}] Upserted {total_upserted} chunks successfully")
            
            # Lexical Ingestion
            print(f"[{index_title}] Starting Lexical Ingestion...")
            lexical_chunks = lexical_chunker.chunk_segments(all_segments, all_links)
            print(f"[{index_title}] Created {len(lexical_chunks)} lexical chunks")
            
            if lexical_chunks:
                es_client = Elasticsearch(
                    os.getenv("ELASTICSEARCH_URL"),
                    api_key=os.getenv("ELASTICSEARCH_API_KEY")
                )
                
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
                
                print(f"[{index_title}] Ingesting {len(actions)} lexical chunks into Elasticsearch...")
                try:
                    success, failed = bulk(es_client, actions, stats_only=True)
                    print(f"[{index_title}] Lexical Ingestion Complete: {success} successful, {failed} failed")
                except Exception as e:
                    print(f"[{index_title}] Error during lexical ingestion: {e}")
                    self._log_error(index_title, "lexical_bulk", "lexical_ingestion_error", str(e), None)
            
            print(f"[{index_title}] Ingestion complete. Processed {len(all_segments)} new segments, skipped {skipped_count}")


def process_book_async(
    book: str, 
    log_file: Optional[Path], 
    error_log_file: Optional[Path], 
    tree_file: Optional[Path], 
    limit: int, 
    resume: bool,
    shared_log: Optional[Dict] = None,
    shared_error_log: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Process a single book using async I/O.
    This function will be called in a separate process.
    """
    try:
        print(f"[PROCESS] Starting ingestion for: {book}")
        
        # Create new event loop for this process
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        ingester = AsyncTextIngester(
            log_file=log_file, 
            error_log_file=error_log_file, 
            tree_file=tree_file,
            shared_log=shared_log,
            shared_error_log=shared_error_log
        )
        
        loop.run_until_complete(ingester.ingest_index(book, limit, resume=resume))
        loop.close()
        
        print(f"[PROCESS] Completed ingestion for: {book}")
        return {"book": book, "status": "success"}
    except Exception as e:
        print(f"[PROCESS] Error processing book {book}: {e}")
        return {"book": book, "status": "error", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Ingest Sefaria texts into vector database (Optimized).")
    parser.add_argument("--titles", nargs='+', default=["Halakhah"], help="Category or book titles from tree to ingest")
    parser.add_argument("--limit", type=int, default=999999, help="Limit number of segments to process per index")
    parser.add_argument("--no-resume", action="store_true", help="Don't resume from previous ingestion")
    parser.add_argument("--log-file", type=str, default=None, help="Path to ingestion log file")
    parser.add_argument("--error-log-file", type=str, default=None, help="Path to error log file")
    parser.add_argument("--tree-file", type=str, default=None, help="Path to sefaria_tree.json file")
    parser.add_argument("--max-workers", type=int, default=10, help="Maximum number of parallel processes (default: 10)")
    args = parser.parse_args()

    log_file = Path(args.log_file) if args.log_file else None
    error_log_file = Path(args.error_log_file) if args.error_log_file else None
    tree_file = Path(args.tree_file) if args.tree_file else None
    
    navigator = TreeNavigator(tree_file=tree_file)

    all_books = []
    for title in args.titles:
        books = navigator.get_books_under_title(title)
        if not books:
            print(f"⚠️  No books found under '{title}'. It might be a book name (not a category).")
            books = [title]
        all_books.extend(books)
    
    all_books = list(set(all_books))
    
    print(f"Found {len(all_books)} unique books to ingest from {len(args.titles)} title(s).")
    print(f"Books: {', '.join(all_books[:10])}{'...' if len(all_books) > 10 else ''}")
    print(f"Processing with {args.max_workers} parallel PROCESSES (each with async I/O)...")
    if error_log_file:
        print(f"Error log will be saved to: {error_log_file}")

    # Use multiprocessing Manager for shared state
    manager = Manager()
    shared_log = manager.dict()
    shared_error_log = manager.dict()

    results = []
    start_time = time.time()
    
    # Use ProcessPoolExecutor for true parallelism
    with ProcessPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_book = {
            executor.submit(
                process_book_async, 
                book, 
                log_file, 
                error_log_file, 
                tree_file, 
                args.limit, 
                not args.no_resume,
                shared_log,
                shared_error_log
            ): book 
            for book in all_books
        }
        
        for future in as_completed(future_to_book):
            book = future_to_book[future]
            try:
                result = future.result()
                results.append(result)
                print(f"✓ Completed: {book}")
            except Exception as e:
                print(f"✗ Exception for book {book}: {e}")
                results.append({"book": book, "status": "error", "error": str(e)})

    elapsed_time = time.time() - start_time
    successful = sum(1 for r in results if r.get("status") == "success")
    failed = len(results) - successful
    
    print(f"\n{'='*50}")
    print(f"All books processed in {elapsed_time:.2f} seconds")
    print(f"Successful: {successful}, Failed: {failed}")
    print(f"Average time per book: {elapsed_time / len(all_books):.2f}s")
    print(f"{'='*50}")
    
    if failed > 0:
        print("\nFailed books:")
        for result in results:
            if result.get("status") == "error":
                print(f"  - {result['book']}: {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    main()
