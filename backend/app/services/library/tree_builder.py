import json
import sys
import os
import asyncio
import aiohttp
import re
from typing import List, Dict, Any, Optional
from pathlib import Path

# Add backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

def encode_hebrew_numeral(n):
    """Simple Hebrew numeral converter (Gematria)."""
    if n <= 0: return str(n)
    
    letters = [
        (400, "ת"), (300, "ש"), (200, "ר"), (100, "ק"),
        (90, "צ"), (80, "פ"), (70, "ע"), (60, "ס"), (50, "נ"), (40, "מ"), (30, "ל"), (20, "כ"), (10, "י"),
        (9, "ט"), (8, "ח"), (7, "ז"), (6, "ו"), (5, "ה"), (4, "ד"), (3, "ג"), (2, "ב"), (1, "א")
    ]
    
    result = ""
    remainder = n
    
    for val, let in letters:
        while remainder >= val:
            result += let
            remainder -= val
            
    # Special cases for 15 (tu) and 16 (tz)
    result = result.replace("יה", "טו").replace("יו", "טז")
    
    # Add geresh for single letter, gershayim for multiple
    if len(result) == 1:
        result += "׳"
    elif len(result) > 1:
        result = result[:-1] + "״" + result[-1]
    
    return result

class APITreeBuilder:
    def __init__(self):
        self.base_url = "https://www.sefaria.org/api"
        self.tree = []
        self.session = None
        self.active_tasks = 0
        self.max_concurrent_tasks = 0
        self.all_books = []
        self.book_results = {}
        self.failed_books = []
        self.terms_cache = {}  # Cache for shared titles (Terms)
        self.base_dir = Path(__file__).resolve().parents[3]
        self.chunk_dir = self.base_dir / "library_chunks"
        self.tree_file = self.base_dir / "sefaria_tree.json"
        self.failed_store = self.chunk_dir / "failed_books.json"
        self.first_available_map = {}

    def slugify(self, value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
        return cleaned or "root"

    async def __aenter__(self):
        # Configure connector with higher limits to support 200 concurrent connections
        connector = aiohttp.TCPConnector(
            limit=1000,  # Total connection limit
            limit_per_host=1000,  # Per-host connection limit (Sefaria API)
            ttl_dns_cache=1000  # DNS cache TTL in seconds
        )
        self.session = aiohttp.ClientSession(connector=connector)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_table_of_contents(self) -> List[Dict[str, Any]]:
        """Fetch the table of contents from Sefaria API."""
        url = f"{self.base_url}/index/"
        async with self.session.get(url) as response:
            if response.status == 200:
                return await response.json()
            else:
                raise Exception(f"Failed to fetch table of contents: {response.status}")

    async def fetch_book_details(self, title: str, max_retries: int = 3) -> Dict[str, Any]:
        """Fetch detailed information about a specific book with retry logic."""
        # Replace spaces with underscores for the API
        url_title = title.replace(" ", "_").replace(",", "%2C")  
        # IMPORTANT: Add with_content_counts=1 to get section counts in the schema
        url = f"{self.base_url}/v2/index/{url_title}?with_content_counts=1"
        
        for attempt in range(max_retries):
            try:
                async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:  # Rate limit
                        wait_time = 2 ** attempt  # Exponential backoff
                        print(f"Rate limited for {title}, waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        print(f"Warning: Failed to fetch details for {title}: {response.status}")
                        return None
            except asyncio.TimeoutError:
                print(f"Timeout fetching {title} (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return None
            except Exception as e:
                print(f"Error fetching {title}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return None
        
        return None

    async def fetch_best_version(self, title: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """Fetch the best (highest priority) Hebrew version for a book."""
        # Replace spaces with underscores for the API
        url_title = title.replace(" ", "_").replace(",", "%2C")
        url = f"{self.base_url}/texts/versions/{url_title}"
        
        for attempt in range(max_retries):
            try:
                async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        versions = await response.json()
                        
                        # Filter for Hebrew versions
                        hebrew_versions = [v for v in versions if v.get("language") == "he"]
                        
                        if not hebrew_versions:
                            return None
                        
                        # Sort by priority (higher is better), handle missing priority
                        hebrew_versions.sort(key=lambda v: float(v.get("priority", 0) or 0), reverse=True)
                        
                        # Return the highest priority version
                        best = hebrew_versions[0]
                        return {
                            "versionTitle": best.get("versionTitle"),
                            "versionSource": best.get("versionSource"),
                            "priority": best.get("priority")
                        }
                    elif response.status == 429:  # Rate limit
                        wait_time = 2 ** attempt
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        return None
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return None
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return None
        
        return None

    def parse_first_available_ref(self, ref: str) -> Optional[tuple]:
        match = re.search(r"([0-9]+)([ab])", ref)
        if not match:
            return None
        return (int(match.group(1)), match.group(2))

    def compute_talmud_start_index(self, start_ref: Optional[tuple]) -> int:
        if not start_ref:
            return 0
        daf, amud = start_ref
        if not daf:
            return 0
        index = (daf - 2) * 2
        if amud == "b":
            index += 1
        return max(0, index)

    async def fetch_first_available(self, title: str, max_retries: int = 3) -> Optional[tuple]:
        url_title = title.replace(" ", "_").replace(",", "%2C")
        url = f"{self.base_url}/texts/{url_title}"
        for attempt in range(max_retries):
            try:
                async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status == 200:
                        data = await response.json()
                        ref = data.get("firstAvailableSectionRef")
                        if ref:
                            return self.parse_first_available_ref(ref)
                        return None
                    elif response.status == 429:
                        wait_time = 2 ** attempt
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        return None
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return None
            except Exception:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return None
        return None

    async def fetch_term(self, term_name: str) -> Optional[Dict[str, str]]:
        """Fetch a term (shared title) from Sefaria API and cache it."""
        # Check cache first
        if term_name in self.terms_cache:
            return self.terms_cache[term_name]
        
        # Replace spaces with underscores for the API
        url_term = term_name.replace(" ", "_")
        url = f"{self.base_url}/terms/{url_term}"
        
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    term_data = await response.json()
                    
                    # Extract English and Hebrew titles
                    titles = term_data.get("titles", [])
                    title_en = term_name  # Default to the term name
                    title_he = term_name
                    
                    for t in titles:
                        if t.get("lang") == "en" and t.get("primary"):
                            title_en = t["text"]
                        elif t.get("lang") == "he" and t.get("primary"):
                            title_he = t["text"]
                    
                    result = {"en": title_en, "he": title_he}
                    self.terms_cache[term_name] = result
                    return result
                else:
                    # If term not found, use the term name itself
                    result = {"en": term_name, "he": term_name}
                    self.terms_cache[term_name] = result
                    return result
        except Exception as e:
            # On error, use the term name itself
            result = {"en": term_name, "he": term_name}
            self.terms_cache[term_name] = result
            return result

    def collect_shared_titles_from_node(self, node: Dict[str, Any], shared_titles: set):
        """Recursively collect all shared titles from a schema node."""
        if "sharedTitle" in node:
            shared_titles.add(node["sharedTitle"])
        
        # Recurse into child nodes
        if "nodes" in node:
            for child_node in node["nodes"]:
                self.collect_shared_titles_from_node(child_node, shared_titles)
    
    async def prefetch_shared_titles(self, book_details_list: List[Dict[str, Any]]):
        """Pre-fetch all shared titles (Terms) from book schemas."""
        shared_titles = set()
        
        # Collect all shared titles from all book schemas
        for book_details in book_details_list:
            if book_details and "schema" in book_details:
                self.collect_shared_titles_from_node(book_details["schema"], shared_titles)
        
        if not shared_titles:
            return
        
        print(f"\nPre-fetching {len(shared_titles)} shared titles (Terms)...")
        
        # Fetch all terms concurrently
        tasks = [self.fetch_term(term) for term in shared_titles]
        await asyncio.gather(*tasks)
        
        print(f"✓ Pre-fetched {len(self.terms_cache)} terms")

    @staticmethod
    def is_content_empty(content: Any) -> bool:
        """Check if content is empty (recursively for nested structures)."""
        if content is None:
            return True
        if isinstance(content, str):
            return not content.strip()
        if isinstance(content, list):
            # Check if all items are empty
            return all(APITreeBuilder.is_content_empty(item) for item in content)
        if isinstance(content, dict):
            # Check if all values are empty
            return all(APITreeBuilder.is_content_empty(v) for v in content.values())
        return False


    def build_section_children(self, book_title: str, book_he_title: str, schema: Dict[str, Any], section_names: List[str], he_section_names: List[str], lengths: List[int], is_talmud: bool = False, start_amud_index: int = 0, total_amud_count: Optional[int] = None) -> List[Dict[str, Any]]:
        """Build children for a book based on its schema, filtering out empty sections."""
        if isinstance(lengths, int):
            lengths = [lengths]
        elif not isinstance(lengths, list):
            lengths = []
        content_counts = schema.get("content_counts", [])
        if not isinstance(content_counts, list):
            content_counts = []
        children = []
        if not lengths and not total_amud_count:
            return children
        num_sections = lengths[0] if lengths else 0
        
        # Get section name (Chapter, Siman, etc.)
        section_name_en = section_names[0] if section_names else "Section"
        section_name_he = he_section_names[0] if he_section_names else "חלק"
        
        # Special handling for Talmud
        if is_talmud and "Daf" in section_name_en:
            total_amud = total_amud_count if total_amud_count is not None else num_sections
            if total_amud is None:
                total_amud = 0
            if total_amud == 0 and lengths:
                total_amud = num_sections
            if total_amud and start_amud_index >= total_amud:
                return children
            final_range = total_amud if total_amud else num_sections
            for amud_index in range(start_amud_index, final_range):
                # Skip empty amudim if content_counts indicate no content
                if content_counts and amud_index < len(content_counts):
                    count = content_counts[amud_index]
                    if count == 0 or count is None or (isinstance(count, list) and len(count) == 0):
                        continue
                    # If count is a nested list, check if it has any nonzero entries
                    if isinstance(count, list):
                        flat_has = False
                        stack = [count]
                        while stack and not flat_has:
                            cur = stack.pop()
                            if isinstance(cur, list):
                                stack.extend(cur)
                            else:
                                try:
                                    if int(cur) != 0:
                                        flat_has = True
                                except Exception:
                                    flat_has = True
                        if not flat_has:
                            continue
                daf_num = 1 + (amud_index // 2)
                amud = 'a' if amud_index % 2 == 0 else 'b'
                he_amud = "." if amud == 'a' else ":"
                he_daf = encode_hebrew_numeral(daf_num)
                children.append({
                    "title": f"Daf {daf_num}{amud}",
                    "heTitle": f"דף {he_daf}{he_amud}",
                    "type": "text",
                    "ref": f"{book_title} {daf_num}{amud}",
                    "heRef": f"{book_he_title} {he_daf}{he_amud}",
                    "children": []
                })
        else:
            # Regular numbering for other books
            for i in range(1, num_sections + 1):
                # Skip if we have content_counts and this section is empty
                section_index = i - 1
                if content_counts and section_index < len(content_counts):
                    count = content_counts[section_index]
                    # Skip if count is 0, None, or empty list
                    if count == 0 or count is None or (isinstance(count, list) and len(count) == 0):
                        continue
                
                he_num = encode_hebrew_numeral(i)
                children.append({
                    "title": f"{section_name_en} {i}",
                    "heTitle": f"{section_name_he} {he_num}",
                    "type": "text",
                    "ref": f"{book_title} {i}",
                    "heRef": f"{book_he_title} {he_num}",
                    "children": []
                })
        
        return children

    def process_jagged_array_node(self, node: Dict[str, Any], parent_ref_en: str, parent_ref_he: str, is_talmud: bool = False, start_amud_index: int = 0) -> List[Dict[str, Any]]:
        """Process a JaggedArrayNode and return its children (sections)."""
        section_names = node.get("sectionNames", [])
        he_section_names = node.get("heSectionNames", [])
        
        # Get lengths - prefer content_counts over lengths field
        content_counts = node.get("content_counts", [])
        if "content_counts" in node:
            content_counts = node["content_counts"]
        lengths = node.get("lengths", [])
        if isinstance(lengths, int):
            lengths = [lengths]
        elif not isinstance(lengths, list):
            lengths = []
        if not lengths and isinstance(content_counts, list):
            lengths = [len(content_counts)]
        total_amud_count = len(content_counts) if isinstance(content_counts, list) else None
        
        return self.build_section_children(
            parent_ref_en, parent_ref_he, node, section_names, he_section_names, lengths, is_talmud, start_amud_index, total_amud_count
        )
    
    def process_complex_node(self, node: Dict[str, Any], parent_ref_en: str, parent_ref_he: str, is_talmud: bool = False, start_amud_index: int = 0) -> Dict[str, Any]:
        """
        Recursively process a node in a complex schema tree.
        Returns a node dictionary with children.
        """
        node_type = node.get("nodeType")
        
        # Get node titles
        node_titles = node.get("titles", [])
        shared_title = node.get("sharedTitle")
        node_key = node.get("key", "")
        
        # Determine English and Hebrew titles
        title_en = ""
        title_he = ""
        
        if shared_title:
            # Look up shared title from cache
            if shared_title in self.terms_cache:
                term_data = self.terms_cache[shared_title]
                title_en = term_data.get("en", shared_title)
                title_he = term_data.get("he", shared_title)
            else:
                # If not in cache, use the shared title value directly
                title_en = shared_title
                title_he = shared_title
        else:
            # Extract from titles array
            for t in node_titles:
                if t.get("lang") == "en" and t.get("primary"):
                    title_en = t["text"]
                elif t.get("lang") == "he" and t.get("primary"):
                    title_he = t["text"]
        
        # Handle default nodes (they don't add to the reference path)
        is_default = node.get("default", False) or node_key == "default"
        
        # Build references
        if is_default:
            # Default nodes don't add to the path
            ref_en = parent_ref_en
            ref_he = parent_ref_he
        else:
            # Non-default nodes add to the path
            if title_en:
                ref_en = f"{parent_ref_en}, {title_en}" if parent_ref_en else title_en
                ref_he = f"{parent_ref_he}, {title_he}" if parent_ref_he else title_he
            else:
                ref_en = parent_ref_en
                ref_he = parent_ref_he
        
        # Process based on node type
        if node_type == "JaggedArrayNode":
            # This is a content node
            section_lengths = node.get("lengths", [])
            if isinstance(section_lengths, int):
                section_lengths = [section_lengths]
            content_counts = node.get("content_counts", [])
            if not section_lengths and isinstance(content_counts, list):
                section_lengths = [len(content_counts)]
            has_sections = bool(section_lengths and section_lengths[0] > 0)
            if not has_sections:
                # Fallback: if the node has depth/section names, still treat it as a section node
                depth_hint = node.get("depth")
                if depth_hint and isinstance(depth_hint, int) and depth_hint > 0:
                    has_sections = True
                elif node.get("sectionNames"):
                    has_sections = True
            
            if is_default:
                return {
                    "type": "default",
                    "children": self.process_jagged_array_node(node, ref_en, ref_he, is_talmud, start_amud_index)
                }
            else:
                # If the jagged node actually has sections, always subdivide (even within complex trees)
                if has_sections:
                    return {
                        "title": title_en,
                        "heTitle": title_he,
                        "type": "section",
                        "ref": ref_en,
                        "heRef": ref_he,
                        "children": self.process_jagged_array_node(node, ref_en, ref_he, is_talmud, start_amud_index)
                    }
                # Otherwise treat as a leaf
                return {
                    "title": title_en,
                    "heTitle": title_he,
                    "type": "text",  # Leaf node type
                    "ref": ref_en,
                    "heRef": ref_he,
                    "children": []
                }
        
        elif node_type == "SchemaNode" or "nodes" in node:
            # This is an intermediate node with children
            children_nodes = node.get("nodes", [])
            processed_children = []
            
            # Process each child recursively
            for child_node in children_nodes:
                processed_child = self.process_complex_node(child_node, ref_en, ref_he, is_talmud, start_amud_index)
                
                # Handle default nodes specially
                if processed_child.get("type") == "default":
                    # Merge default node's children directly
                    processed_children.extend(processed_child.get("children", []))
                else:
                    processed_children.append(processed_child)
            
            # Return the schema node with its children
            if is_default:
                return {
                    "type": "default",
                    "children": processed_children
                }
            else:
                return {
                    "title": title_en,
                    "heTitle": title_he,
                    "type": "section",
                    "ref": ref_en,
                    "heRef": ref_he,
                    "children": processed_children
                }
        
        else:
            # Unknown node type - return empty
            return {
                "title": title_en or "Unknown",
                "heTitle": title_he or "לא ידוע",
                "type": "section",
                "ref": ref_en,
                "heRef": ref_he,
                "children": []
            }

    def process_schema_node(self, book_title: str, book_he_title: str, schema: Dict[str, Any], categories: List[str], start_amud_index: int = 0) -> Dict[str, Any]:
        """Process a schema node and return a book node with children."""
        is_talmud = any(cat in categories for cat in ["Bavli", "Yerushalmi", "Talmud"])
        
        node_type = schema.get("nodeType")
        
        # Get titles from schema
        titles = schema.get("titles", [])
        he_title = book_he_title
        for title_obj in titles:
            if title_obj.get("lang") == "he" and title_obj.get("primary"):
                he_title = title_obj["text"]
                break
        
        book_node = {
            "id": book_title,
            "title": book_title,
            "heTitle": he_title,
            "type": "book",
            "categories": categories,
            "ref": book_title,
            "heRef": he_title,
            "children": []
        }
        
        # Case 1: Simple schema - single JaggedArrayNode
        if node_type == "JaggedArrayNode":
            book_node["children"] = self.process_jagged_array_node(
                schema, book_title, he_title, is_talmud, start_amud_index
            )
        
        # Case 2: Complex schema - SchemaNode with children
        elif node_type == "SchemaNode" and "nodes" in schema:
            nodes = schema["nodes"]
            
            # Process all child nodes recursively
            for node in nodes:
                processed = self.process_complex_node(node, book_title, he_title, is_talmud, start_amud_index)
                
                # Handle default nodes
                if processed.get("type") == "default":
                    # Merge default node's children directly into book
                    book_node["children"].extend(processed.get("children", []))
                else:
                    book_node["children"].append(processed)
        
        # Case 3: Schema has nodes at top level (no explicit nodeType)
        elif "nodes" in schema and not node_type:
            nodes = schema["nodes"]
            
            # Process all child nodes recursively
            for node in nodes:
                processed = self.process_complex_node(node, book_title, he_title, is_talmud, start_amud_index)
                
                # Handle default nodes
                if processed.get("type") == "default":
                    # Merge default node's children directly into book
                    book_node["children"].extend(processed.get("children", []))
                else:
                    book_node["children"].append(processed)
        
        return book_node

    def collect_all_books(self, contents: List[Dict[str, Any]]) -> None:
        """Recursively collect all books from the table of contents."""
        for item in contents:
            if "category" in item:
                # Recurse into subcategories
                if "contents" in item:
                    self.collect_all_books(item["contents"])
            elif "title" in item:
                # This is a book, add it to our collection
                self.all_books.append(item)
    
    async def fetch_all_books_batch(self) -> None:
        """Fetch all books in one giant batch with true 200-concurrent processing."""
        if not self.all_books:
            return
        
        total_books = len(self.all_books)
        print(f"\n{'='*60}")
        print(f"Starting batch fetch of {total_books} books with 1000 concurrent connections")
        print(f"{'='*60}\n")
        
        # Create a semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(1000)
        
        # Storage for fetched book details
        book_details_map = {}
        best_versions_map = {}
        start_refs_map = {}
        
        async def fetch_book_data(item):
            async with semaphore:
                # Track active tasks
                self.active_tasks += 1
                current_active = self.active_tasks
                
                # Update max concurrent tasks
                if current_active > self.max_concurrent_tasks:
                    self.max_concurrent_tasks = current_active
                
                print(f"[{current_active} active] Fetching: {item['title']}")
                is_talmud = any(cat in item.get("categories", []) for cat in ["Bavli", "Yerushalmi", "Talmud"])
                
                try:
                    tasks = [
                        self.fetch_book_details(item["title"]),
                        self.fetch_best_version(item["title"])
                    ]
                    if is_talmud:
                        tasks.append(self.fetch_first_available(item["title"]))
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    book_details = results[0]
                    best_version = results[1]
                    start_ref = results[2] if is_talmud else None
                    
                    if isinstance(book_details, Exception):
                        book_details = None
                    if isinstance(best_version, Exception):
                        best_version = None
                    if isinstance(start_ref, Exception):
                        start_ref = None
                    
                    print(f"✓ Fetched: {item['title']}")
                    return (item["title"], item, book_details, best_version, start_ref)
                except Exception as e:
                    print(f"✗ Error fetching {item['title']}: {e}")
                    return (item["title"], item, None, None, None)
                finally:
                    # Decrement active tasks
                    self.active_tasks -= 1
        
        # Fetch all books concurrently
        results = await asyncio.gather(*[fetch_book_data(book) for book in self.all_books])
        
        # Store fetched data
        for title, item, book_details, best_version, start_ref in results:
            book_details_map[title] = (item, book_details)
            if best_version:
                best_versions_map[title] = best_version
            if start_ref:
                start_refs_map[title] = start_ref
        self.first_available_map = start_refs_map
        
        print(f"\n{'='*60}")
        print(f"Batch fetch complete!")
        print(f"Peak concurrent tasks: {self.max_concurrent_tasks}")
        print(f"Total books fetched: {len(book_details_map)}")
        print(f"{'='*60}\n")
        
        # Pre-fetch all shared titles (Terms) from schemas
        all_book_details = [details for _, details in book_details_map.values() if details]
        await self.prefetch_shared_titles(all_book_details)
        
        # Now process all books with terms available
        print("\nProcessing book schemas...")
        for title, (item, book_details) in book_details_map.items():
            try:
                failure_reason = None
                if book_details is None:
                    failure_reason = "Timeout or failed to fetch book details after retries"
                elif "schema" not in book_details:
                    failure_reason = "Book details returned but no schema found"
                
                if book_details and "schema" in book_details:
                    start_idx = 0
                    if title in start_refs_map:
                        start_idx = self.compute_talmud_start_index(start_refs_map.get(title))
                    book_node = self.process_schema_node(
                        item["title"],
                        item.get("heTitle", ""),
                        book_details["schema"],
                        item.get("categories", []),
                        start_idx
                    )
                    
                    if title in best_versions_map:
                        book_node["bestVersion"] = best_versions_map[title]
                    
                    self.book_results[title] = book_node
                else:
                    if failure_reason:
                        self.failed_books.append({
                            "title": item["title"],
                            "reason": failure_reason
                        })
                    else:
                        self.failed_books.append({
                            "title": item["title"],
                            "reason": "No book details or schema returned"
                        })
                    
                    fallback_node = {
                        "id": item["title"],
                        "title": item["title"],
                        "heTitle": item.get("heTitle", ""),
                        "type": "book",
                        "categories": item.get("categories", []),
                        "ref": item["title"],
                        "heRef": item.get("heTitle", ""),
                        "children": []
                    }
                    
                    if title in best_versions_map:
                        fallback_node["bestVersion"] = best_versions_map[title]
                    
                    self.book_results[title] = fallback_node
            except Exception as e:
                print(f"✗ Error processing schema for {item['title']}: {e}")
                self.failed_books.append({
                    "title": item["title"],
                    "reason": f"Exception during processing: {str(e)}"
                })
                fallback_node = {
                    "id": item["title"],
                    "title": item["title"],
                    "heTitle": item.get("heTitle", ""),
                    "type": "book",
                    "categories": item.get("categories", []),
                    "ref": item["title"],
                    "heRef": item.get("heTitle", ""),
                    "children": []
                }
                self.book_results[title] = fallback_node
        
        print(f"\n{'='*60}")
        print(f"Processing complete!")
        print(f"Total books processed: {len(self.book_results)}")
        if self.failed_books:
            print(f"\nFailed books ({len(self.failed_books)}):")
            for failed in self.failed_books:
                print(f"  - {failed['title']}: {failed['reason']}")
        self.save_failed_books()
        print(f"{'='*60}\n")
    
    def rebuild_tree_with_books(self, contents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rebuild the tree structure using pre-fetched book data."""
        result = []
        
        for item in contents:
            if "category" in item:
                # This is a category
                subcat_node = {
                    "title": item.get("category"),
                    "heTitle": item.get("heCategory"),
                    "type": "category",
                    "children": []
                }
                
                # Recurse into subcategories
                if "contents" in item:
                    subcat_node["children"] = self.rebuild_tree_with_books(item["contents"])
                
                result.append(subcat_node)
            elif "title" in item:
                # This is a book, get it from pre-fetched results
                book_title = item["title"]
                if book_title in self.book_results:
                    result.append(self.book_results[book_title])
        
        return result

    async def build(self, retry_failed_only: bool = False, failed_titles: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Build the complete tree from Sefaria API with optimized batch processing."""
        print("Fetching table of contents from Sefaria API...")
        toc = await self.fetch_table_of_contents()
        print(f"Received {len(toc)} top-level categories")
        
        # Step 1: Collect all books from all categories
        print("\nCollecting all books from table of contents...")
        for category in toc:
            if "contents" in category:
                self.collect_all_books(category["contents"])
        print(f"Collected {len(self.all_books)} books total")
        if retry_failed_only and failed_titles:
            titles_set = set(failed_titles)
            self.all_books = [b for b in self.all_books if b.get("title") in titles_set]
            print(f"Retrying subset of failed books: {len(self.all_books)}")
        
        # Step 2: Fetch all books in one giant batch (TRUE 200-concurrent processing)
        await self.fetch_all_books_batch()
        
        # Step 3: Rebuild tree structure with pre-fetched book data
        print("\nRebuilding tree structure...")
        tree = []
        for category in toc:
            category_node = {
                "title": category.get("category"),
                "heTitle": category.get("heCategory"),
                "type": "category",
                "children": [],
                "slug": self.slugify(category.get("category") or category.get("heCategory") or "")
            }
            
            if "contents" in category:
                category_node["children"] = self.rebuild_tree_with_books(category["contents"])
            
            tree.append(category_node)
        
        self.tree = tree
        self.save_chunks()
        print(f"\nTree building complete!")
        print(f"Final tree has {len(self.tree)} top-level categories")
        if self.failed_books:
            print(f"\nSummary: {len(self.failed_books)} books failed to fetch properly")
        
        return self.tree

    def save_to_json(self, filepath: Optional[str] = None):
        target = Path(filepath) if filepath else self.tree_file
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(self.tree, f, indent=2, ensure_ascii=False)
        print(f"Tree saved to {target}")

    def save_chunks(self, base_path: Optional[str] = None):
        base = Path(base_path) if base_path else self.chunk_dir
        base.mkdir(parents=True, exist_ok=True)
        root_nodes = []
        for category in self.tree:
            slug = category.get("slug") or self.slugify(category.get("title") or category.get("heTitle") or "")
            category["slug"] = slug
            root_nodes.append({
                "title": category.get("title"),
                "heTitle": category.get("heTitle"),
                "type": category.get("type"),
                "slug": slug,
                "hasChildren": bool(category.get("children"))
            })
            chunk_path = base / f"{slug}.json"
            with open(chunk_path, "w", encoding="utf-8") as f:
                json.dump(category.get("children", []), f, ensure_ascii=False)
        root_path = base / "root.json"
        with open(root_path, "w", encoding="utf-8") as f:
            json.dump(root_nodes, f, ensure_ascii=False)
        search_entries = []
        def walk(nodes, path_titles, path_he_titles):
            for node in nodes:
                node_title = node.get("title") or ""
                node_he_title = node.get("heTitle") or ""
                current_path = path_titles + [node_title] if node_title else path_titles
                current_he_path = path_he_titles + [node_he_title] if node_he_title else path_he_titles
                node_type = node.get("type")
                if node_type in ("book", "section", "text"):
                    entry_ref = node.get("ref")
                    search_entries.append({
                        "title": node.get("title"),
                        "heTitle": node.get("heTitle"),
                        "heRef": node.get("heRef"),
                        "ref": entry_ref,
                        "slug": self.slugify(node.get("title") or node.get("heTitle") or ""),
                        "path": current_path[:-1],
                        "path_he": current_he_path[:-1],
                        "type": node_type
                    })
                children = node.get("children") or []
                if children:
                    walk(children, current_path, current_he_path)
        walk(self.tree, [], [])
        search_path = base / "search_index.json"
        with open(search_path, "w", encoding="utf-8") as f:
            json.dump(search_entries, f, ensure_ascii=False)

    def load_failed_titles(self) -> List[str]:
        if not self.failed_store.exists():
            return []
        try:
            with open(self.failed_store, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [d.get("title") for d in data if isinstance(d, dict) and d.get("title")]
                return []
        except Exception:
            return []

    def save_failed_books(self):
        self.failed_store.parent.mkdir(parents=True, exist_ok=True)
        with open(self.failed_store, "w", encoding="utf-8") as f:
            json.dump(self.failed_books, f, ensure_ascii=False)

# For testing
async def main():
    from dotenv import load_dotenv
    load_dotenv("backend/.env")
    
    async with APITreeBuilder() as builder:
        retry_failed_only = os.getenv("RETRY_FAILED_ONLY") == "1"
        if retry_failed_only:
            failed_titles = builder.load_failed_titles()
            if failed_titles:
                print(f"Retrying only failed titles ({len(failed_titles)})")
                await builder.build(retry_failed_only=True, failed_titles=failed_titles)
            else:
                await builder.build()
        else:
            await builder.build()
        builder.save_to_json()

if __name__ == "__main__":
    asyncio.run(main())
