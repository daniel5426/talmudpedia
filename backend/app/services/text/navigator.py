import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

@dataclass
class RangeContext:
    raw: Optional[Dict[str, str]]
    start: Optional[Dict[str, Any]]
    end: Optional[Dict[str, Any]]


class ReferenceNavigator:
    DAF_PATTERN = re.compile(r"(.*?)(\d+)([ab])(?:[: ](\d+))?$", re.IGNORECASE)
    CHAPTER_PATTERN = re.compile(r"(.*?)(\d+)(?:[: ](\d+))?$")

    @classmethod
    def parse_ref(cls, ref: str) -> Dict[str, Any]:
        """Parses Sefaria references into structured metadata, handling multi-part titles."""
        original_ref = ref
        parsed_data: Dict[str, Any] = {"index": ref} # Default to full ref as index

        ref_stripped = ref.strip()
        daf_match = cls.DAF_PATTERN.match(ref_stripped)
        if daf_match:
            prefix, daf_num, daf_side, line_num = daf_match.groups()
            parsed_data["daf_num"] = int(daf_num)
            parsed_data["side"] = daf_side.lower()
            parsed_data["daf"] = f"{parsed_data['daf_num']}{parsed_data['side']}"
            if line_num:
                parsed_data["line"] = int(line_num)
            index_title = prefix.strip()
            if index_title:
                parsed_data["index"] = index_title
        else:
            chapter_match = cls.CHAPTER_PATTERN.match(ref_stripped)
            if chapter_match:
                prefix, chapter_num, verse_num = chapter_match.groups()
                parsed_data["chapter"] = int(chapter_num)
                if verse_num:
                    parsed_data["verse"] = int(verse_num)
                index_title = prefix.strip()
                if index_title:
                    parsed_data["index"] = index_title

        if parsed_data["index"].endswith(',') or parsed_data["index"].endswith(':'):
            parsed_data["index"] = parsed_data["index"].rstrip(',:').strip()

        return parsed_data

    @classmethod
    def parse_range_ref(cls, ref: str) -> Optional[Dict[str, str]]:
        """Detects range references and returns their boundaries."""
        if "-" not in ref:
            return None
        parts = ref.split("-")
        if len(parts) != 2:
            return None
        start_ref = parts[0].strip()
        end_ref = parts[1].strip()
        start_parsed = cls.parse_ref(start_ref)
        if "index" not in start_parsed:
            return None
        return {"start": start_ref, "end": end_ref}

    @classmethod
    def get_adjacent_refs(cls, ref: str, offset: int) -> Optional[str]:
        """Calculates neighboring page references based on offset."""
        if offset == 0:
            return ref
        parsed = cls.parse_ref(ref)
        index_title = parsed["index"]
        if "daf" in parsed:
            daf_num = parsed["daf_num"]
            side = parsed["side"]
            # Sefaria's linear index for daf starts from 2a as index 0.
            # So 2a is (2-2)*2 + 0 = 0
            # 2b is (2-2)*2 + 1 = 1
            # 3a is (3-2)*2 + 0 = 2
            linear_index = (daf_num - 2) * 2 + (0 if side == 'a' else 1)
            new_linear_index = linear_index + offset
            if new_linear_index < 0:
                return None
            
            # Convert back to daf_num and side
            new_daf_num = (new_linear_index // 2) + 2
            new_side = 'a' if new_linear_index % 2 == 0 else 'b'
            return f"{index_title} {new_daf_num}{new_side}"
        if "chapter" in parsed and parsed["chapter"] is not None:
            new_chapter = parsed["chapter"] + offset
            if new_chapter < 1:
                return None
            return f"{index_title} {new_chapter}"
        return None

    @classmethod
    def is_in_range(cls, current_idx: int, current_page_parsed: Dict[str, Any], range_ctx: RangeContext) -> bool:
        """Checks if a segment index lives inside the requested range."""
        if not range_ctx.raw or not range_ctx.start or not range_ctx.end:
            return False
        is_start_page = False
        start_idx = -1
        if "daf" in current_page_parsed and "daf" in range_ctx.start:
            if current_page_parsed["daf"] == range_ctx.start["daf"]:
                is_start_page = True
                start_idx = range_ctx.start.get("line", 1) - 1
        elif "chapter" in current_page_parsed and "chapter" in range_ctx.start:
            if current_page_parsed["chapter"] == range_ctx.start["chapter"]:
                is_start_page = True
                start_idx = range_ctx.start.get("verse", 1) - 1
        is_end_page = False
        end_idx = 999999
        if "daf" in current_page_parsed and "daf" in range_ctx.end:
            if current_page_parsed["daf"] == range_ctx.end["daf"]:
                is_end_page = True
                end_idx = range_ctx.end.get("line", 999999) - 1
        elif "chapter" in current_page_parsed and "chapter" in range_ctx.end:
            if current_page_parsed["chapter"] == range_ctx.end["chapter"]:
                is_end_page = True
                end_idx = range_ctx.end.get("verse", 999999) - 1
        if is_start_page and is_end_page:
            return start_idx <= current_idx <= end_idx
        if is_start_page and not is_end_page:
            return current_idx >= start_idx
        if is_end_page and not is_start_page:
            return current_idx <= end_idx
        return False

    @classmethod
    def get_ref_from_index(cls, index_title: str, index: int, is_talmud: bool) -> str:
        """Reconstructs a reference string from a linear index."""
        if is_talmud:
            # For Talmud here we map array index directly: index 0 -> 1a, 1 -> 1b, 2 -> 2a, etc.
            # So daf_num = (index // 2) + 1
            daf_num = (index // 2) + 1
            side = 'a' if index % 2 == 0 else 'b'
            return f"{index_title} {daf_num}{side}"
        else:
            # For chapter-based texts, index 0 corresponds to chapter 1, etc.
            return f"{index_title} {index + 1}"

    @classmethod
    def get_ref_from_linear(cls, index_title: str, linear_index: int) -> str:
        daf_num = (linear_index // 2) + 1
        side = 'a' if linear_index % 2 == 0 else 'b'
        return f"{index_title} {daf_num}{side}"

    @classmethod
    def tokenize_ref(cls, ref: str) -> List[str]:
        """
        Splits a reference string into semantic tokens.
        Handles spaces, colons, commas, periods as separators.
        e.g. "Genesis 1:1" -> ["Genesis", "1", "1"]
        e.g. "Sefer Mitzvot Gadol, Positive Commandments:2" -> ["Sefer", "Mitzvot", "Gadol", "Positive", "Commandments", "2"]
        """
        import re
        # We split by one or more separator chars.
        # We preserve words.
        # Note: Titles with spaces will be split into multiple tokens.
        parts = re.split(r'[:,\. \-]+', ref)
        return [p for p in parts if p]


class ComplexTextNavigator:
    """Handles navigation through complex text structures using the Index Schema."""
    
    @staticmethod
    def navigate_to_section(text_data: Dict[str, Any], schema: Dict[str, Any], ref: str, index_doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Navigate through a complex text structure to find the content for a given reference.
        
        Args:
            text_data: The full text document from MongoDB
            schema: The schema for the index
            ref: The reference string (e.g., "Sefer Mitzvot Gadol, Positive Commandments, Remazim")
            index_doc: Optional index document from MongoDB for fallback Hebrew title retrieval
        
        Returns:
            Dict containing:
            - content: The text content (list of segments)
            - heRef: The constructed Hebrew reference string
            - ref: The resolved English reference
            - is_complex: Boolean indicating if we navigated a complex structure
        """
        parsed_ref = ReferenceNavigator.parse_ref(ref)
        
        # Get the root content
        root_content = text_data.get("chapter", [])
        if isinstance(root_content, dict) and 'default' in root_content and len(root_content) == 1:
            root_content = root_content['default']
            
        # If it's a simple text (JaggedArray at root), handle directly
        if schema.get("nodeType") == "JaggedArrayNode":
            # Simple text navigation handled by standard logic, but let's support it here too
            return {
                "content": root_content,
                "heRef": text_data.get("heTitle", ""),
                "ref": text_data.get("title", ""),
                "is_complex": False
            }

        # For complex texts, we need to traverse the schema
        # Tokenize the reference for robust matching (Sefaria-style)
        # e.g. "Sefer Mitzvot Gadol, Positive Commandments:2" -> ["Sefer", "Mitzvot", "Gadol", "Positive", "Commandments", "2"]
        tokens = ReferenceNavigator.tokenize_ref(ref)
        
        # Determine Hebrew Title to skip if present in tokens
        he_book_title = text_data.get("heTitle")
        if not he_book_title:
             # Try schema first
             he_book_title = next((t["text"] for t in schema.get("titles", []) if t.get("primary") and t.get("lang") == "he"), "")
             
             # If still not found, try index_doc as fallback
             if not he_book_title and index_doc:
                 he_book_title = index_doc.get("heTitle", "")
        
        # Determine the effective root reference of this document (handles split texts)
        doc_root_ref = text_data.get("sectionRef") or text_data.get("title")
        doc_root_tokens = ReferenceNavigator.tokenize_ref(doc_root_ref)
        
        # Default start at root
        current_node = schema
        current_tokens = tokens
        
        # Navigate schema to find the node corresponding to doc_root_ref
        # First, match schema title tokens
        matched_root_tokens = 0
        schema_titles = schema.get("titles", [])
        for t in schema_titles:
             if t.get("lang") == "en":
                 t_toks = ReferenceNavigator.tokenize_ref(t["text"])
                 if len(doc_root_tokens) >= len(t_toks) and \
                    all(doc_root_tokens[i].lower() == t_toks[i].lower() for i in range(len(t_toks))):
                         matched_root_tokens = len(t_toks)
                         break
        
        # Traverse children to reach the partial document node
        nav_tokens = doc_root_tokens[matched_root_tokens:]
        while nav_tokens and "nodes" in current_node:
            found = False
            for child in current_node.get("nodes", []):
                # Check titles and key
                candidates = [t["text"] for t in child.get("titles", []) if t.get("lang") == "en"]
                if child.get("key"): candidates.append(child.get("key"))
                
                for cand in candidates:
                     c_toks = ReferenceNavigator.tokenize_ref(cand)
                     if len(nav_tokens) >= len(c_toks) and \
                        all(nav_tokens[k].lower() == c_toks[k].lower() for k in range(len(c_toks))):
                             current_node = child
                             nav_tokens = nav_tokens[len(c_toks):]
                             found = True
                             break
                if found: break
            if not found: break
            
        # Update current_tokens to be relative to the current_node (strip doc path)
        if len(tokens) >= len(doc_root_tokens) and \
           all(tokens[i].lower() == doc_root_tokens[i].lower() for i in range(len(doc_root_tokens))):
               current_tokens = tokens[len(doc_root_tokens):]
        else:
             # Fallback: if ref doesn't match doc path, try stripping just index title
             index_title_tokens = ReferenceNavigator.tokenize_ref(text_data.get("title", ""))
             if len(tokens) >= len(index_title_tokens) and \
                all(tokens[i].lower() == index_title_tokens[i].lower() for i in range(len(index_title_tokens))):
                    current_tokens = tokens[len(index_title_tokens):]

        current_content = root_content
        
        he_ref_parts = [he_book_title] if he_book_title else []
        
        return ComplexTextNavigator._traverse_tokens(
            current_node,
            current_content,
            current_tokens,
            he_ref_parts,
            parsed_ref
        )


    @staticmethod
    def strip_book_title_from_heref(full_heref: str) -> str:
        """
        Strips the book title from a Hebrew reference to show just the relevant segment/section.
        
        Examples:
            "ספר החינוך ב'" -> "ב'"
            "ספר מצוות גדול, עשין, רמזים" -> "רמזים"
            "ספר מצוות גדול, עשין, רמזים א'" -> "רמזים א'"
            "בראשית א:ב" -> "א:ב"
        """
        if not full_heref:
            return full_heref
            
        # If there's a comma, it's a multi-part reference (book, section, subsection)
        # We want to keep just the last meaningful part
        if ", " in full_heref:
            # Split by commas
            parts = full_heref.split(", ")
            # Return the last part (most specific section)
            return parts[-1] if parts else full_heref
        
        # For simple refs like "ספר החינוך ב'", we want to strip the book title
        # and keep just the segment number
        # Look for the last space followed by Hebrew letters/numbers
        parts = full_heref.rsplit(" ", 1)
        if len(parts) == 2:
            # Check if the second part looks like a segment identifier (has Hebrew letters)
            last_part = parts[1]
            if any('\u0590' <= c <= '\u05FF' for c in last_part):  # Hebrew Unicode range
                return last_part
        
        # Fallback: return as-is
        return full_heref

    @staticmethod
    def encode_hebrew_numeral(n: int) -> str:
        """Simple Gematria helper for 1-999."""
        if n <= 0:
            return str(n)
        
        ones = ["", "א", "ב", "ג", "ד", "ה", "ו", "ז", "ח", "ט"]
        tens = ["", "י", "כ", "ל", "מ", "נ", "ס", "ע", "פ", "צ"]
        hundreds = ["", "ק", "ר", "ש", "ת"]

        parts: List[str] = []
        value = n

        # Handle 400+ by peeling off tavs greedily (e.g., 500 => ת + ק, 900 => תת"ק)
        while value >= 400:
            parts.append("ת")
            value -= 400

        # Remaining hundreds (0-300)
        h = value // 100
        if h:
            parts.append(hundreds[h])
            value -= h * 100

        # Tens / ones with special cases for 15,16
        t = value // 10
        o = value % 10
        if t == 1 and o in (5, 6):
            parts.append("טו" if o == 5 else "טז")
        else:
            if t:
                parts.append(tens[t])
            if o:
                parts.append(ones[o])

        result = "".join(parts)

        # Add Geresh/Gershayim
        if len(result) == 1:
            result += "'"
        elif len(result) > 1:
            result = result[:-1] + '"' + result[-1]

        return result

    @staticmethod
    def get_prev_section_ref(index_title: str, schema: Dict[str, Any], current_ref: str) -> Optional[str]:
        """
        Finds the reference for the PREVIOUS logical section in the schema.
        Used when scrolling UP.
        """

        ref_parts = ReferenceNavigator.tokenize_ref(current_ref) # tokenize!
        path = ComplexTextNavigator._find_schema_path_tokens(schema, ref_parts) # use tokens
        if not path:
            print(f"DEBUG: get_prev_section_ref failed to find path for {current_ref}")
            return None
            
        for i in range(len(path) - 1, -1, -1):
            curr_node, _ = path[i]
            if i == 0:
                break
                
            parent_node, parent_ref_prefix = path[i-1]
            if "nodes" not in parent_node:
                continue
                
            children = parent_node["nodes"]
            try:
                curr_idx = next(idx for idx, child in enumerate(children) if child.get("key") == curr_node.get("key"))
            except StopIteration:
                continue
                
            if curr_idx > 0:
                prev_sibling = children[curr_idx - 1]
                # We need to construct the HeRef (or just Ref?) for this sibling.
                # Actually we return English Ref.
                
                # We need the prefix titles.
                # path[i-1] has the node, but what is the title string accumulated so far?
                # _find_schema_path_tokens returns (node, title_part).
                # But title_part is just the text matched.
                
                # We should reconstruct the ref from the path titles up to start of sibling.
                # Actually, `path` contains the nodes traversed. 
                # We can rebuild the ref string from the `titles` of the nodes in `path[:i]`.
                
                # Wait, ReferenceNavigator.tokenize_ref breaks it down.
                # Rebuilding is tricky.
                # Better: Use the `ref_parts` we parsed? No, we might switch branch.
                
                # Strategy: Reconstruct Ref from Root to Parent.
                # Then add Sibling Title.
                
                # Since we don't have stored Ref strings in path (only titles matched or ""):
                # We iterate path[:i]. For each node (except root?), get primary EN title.
                
                ref_builder = []
                # Index title first?
                # Root node usually matches index title?
                # Our path finding starts at `schema`, which is root.
                # Usually we want "IndexTitle, NodeTitle..."
                
                # The `index_title` arg is passed! Use that.
                ref_builder.append(index_title)
                
                # Check path nodes between root and parent (exclusive of root, inclusive of parent)
                for k in range(1, i): # 1 to i-1
                     p_node, _ = path[k]
                     p_title = next((t["text"] for t in p_node.get("titles", []) if t.get("primary") and t.get("lang") == "en"), p_node.get("key"))
                     ref_builder.append(p_title)
                
                # Now add Previous Sibling Title (ONLY IF NOT DEFAULT)
                # DELETED - Handled by _drill_to_last_leaf
                
                # Now drill to last leaf of sibling
                prev_leaf_ref_parts = ComplexTextNavigator._drill_to_last_leaf(prev_sibling)
                ref_builder.extend(prev_leaf_ref_parts)
                
                final_ref = ", ".join(ref_builder)
                return final_ref
                
        return None

    @staticmethod
    def get_next_section_ref(index_title: str, schema: Dict[str, Any], current_ref: str) -> Optional[str]:
        """
        Finds the reference for the NEXT logical section in the schema.
        Used when pagination reaches the end of the current section.
        """

        ref_parts = ReferenceNavigator.tokenize_ref(current_ref) # tokenize!
        path = ComplexTextNavigator._find_schema_path_tokens(schema, ref_parts) # use tokens
        if not path:
            return None
            
        # Path is list of (node, ref_part_used_to_match)
        # We start from the leaf (end of path) and look for next sibling
        
        # Traverse up from leaf
        for i in range(len(path) - 1, -1, -1):
            curr_node, _ = path[i]
            
            # If we are at root (i=0), and we haven't found a next sibling yet, we are done (end of book)
            if i == 0:
                break
                
            parent_node, parent_ref_prefix = path[i-1]
            if "nodes" not in parent_node:
                continue
                
            children = parent_node["nodes"]
            try:
                curr_idx = next(idx for idx, child in enumerate(children) if child.get("key") == curr_node.get("key"))
            except StopIteration:
                continue
                
            # Check if there is a next sibling
            if curr_idx < len(children) - 1:
                next_sibling = children[curr_idx + 1]
                
                # Found the branch point!
                # We need to construct the Ref for this new sibling.
                # Ref = [Index CurrentPrefix...] + [Sibling Title] + [First Leaf of Sibling...]
                
                # Reconstruct prefix from path
                ref_builder = []
                ref_builder.append(index_title)
                
                for k in range(1, i):
                     p_node, _ = path[k]
                     p_title = next((t["text"] for t in p_node.get("titles", []) if t.get("primary") and t.get("lang") == "en"), p_node.get("key"))
                     ref_builder.append(p_title)
                
                # Add Sibling Title (ONLY IF NOT DEFAULT)
                # DELETED - Handled by _drill_to_first_leaf
                
                # Drill to first leaf of this sibling
                leaf_parts = ComplexTextNavigator._drill_to_first_leaf(next_sibling)
                ref_builder.extend(leaf_parts)
                
                final_ref = ", ".join(ref_builder)
                return final_ref

        return None

    @staticmethod
    def _find_schema_path_tokens(root_node: Dict[str, Any], tokens: List[str]) -> List[Tuple[Dict[str, Any], str]]:
        """
        Returns a list of (Node, TitleString) representing the path to the node matching tokens.
        Greedy token matching.
        """
        path = []
        curr = root_node
        
        # We assume root node matches start of tokens? 
        # Usually path starts with the Index Node.
        # But tokens might include Index Title. 
        # _find_schema_path usually expects ref_parts relative to... wait.
        # get_next_section_ref passes `schema` as root.
        # Schema root usually corresponds to Index Title.
        
        # Consume tokens matching root node title?
        # Actually, get_next_section_ref input `current_ref` includes Index Title.
        # So we should try to match Index Title first.
        
        # Let's record the root (Index)
        # Note: root_node passed in IS the schema (index) node.
        
        # Check if root node matches start of tokens?
        # Actually `schema` node usually doesn't have `titles` (it's in the index doc).
        # But for traversal sake, we start at root.
        
        # Optimization: We assume caller handles index title stripping OR we just match whatever we can.
        # But for accurate path finding, we need to match the tokens to the nodes.
        
        # If tokens[0] is "Sefer", tokens[1] is "Mitzvot"... matches Index Title.
        # We record root node and advance tokens.
        
        # Wait, previous implementation `_find_schema_path` took `root_node` (schema) and `ref_parts`.
        # It added `(curr, root_part)` to path immediately.
        
        path.append((curr, "")) # Root node. Title recorded? Maybe unnecessary for next/prev logic which cares about structure.
        
        # We need to traverse down consuming tokens.
        remaining_tokens = tokens[:]
        
        # Consume Index Title tokens if present?
        # The schema root usually represents the whole book.
        # If valid ref, it starts with book title.
        # If we can't verify book title (no titles on schema root), we might just skip tokens?
        # Or assumes strict structure.
        
        # Let's assume we need to match children.
        # But if tokens contain "Sefer Mitzvot Gadol", and children are "Positive Commandments", we must consume "SMG" first.
        # We don't have titles here easily (passed as root_node dict).
        
        # HACK/Strategy: Try to match children with current tokens. 
        # If no child matches, try skipping one token? (Risk of skipping real content).
        # BETTER: Try to match children. If no child matches, check if we are at root. 
        # If at root, maybe tokens start with Index Title?
        # Iterate children. If match found, great.
        # If no match found, maybe strip first token and try again? (Title consumption).
        
        # Safety: Only strip up to N tokens?
        
        curr_tokens = remaining_tokens
        
        while curr_tokens or ("nodes" in curr and any(c.get("default") for c in curr["nodes"])):
            if not curr_tokens:
                if "nodes" in curr:
                    def_child = next((c for c in curr["nodes"] if c.get("default")), None)
                    if def_child:
                        curr = def_child
                        path.append((curr, "")) 
                        break
                break

            found = False
            
            if "nodes" in curr:
                # Try to match children
                for child in curr["nodes"]:
                    child_titles = child.get("titles", [])
                    matched_count = 0
                    
                    for t in child_titles:
                        # Check all titles (he/en)
                        if t.get("text"):
                            t_toks = ReferenceNavigator.tokenize_ref(t["text"])
                            if len(curr_tokens) >= len(t_toks):
                                match = True
                                for k in range(len(t_toks)):
                                    if curr_tokens[k].lower() != t_toks[k].lower():
                                        match = False
                                        break
                                if match:
                                    matched_count = len(t_toks)
                                    break
                    
                    if matched_count == 0:
                         key = child.get("key", "")
                         key_toks = ReferenceNavigator.tokenize_ref(key)
                         if len(curr_tokens) >= len(key_toks):
                                match = True
                                for k in range(len(key_toks)):
                                    if curr_tokens[k].lower() != key_toks[k].lower():
                                        match = False
                                        break
                                if match:
                                    matched_count = len(key_toks)
                    
                    if matched_count > 0:
                        curr = child
                        path.append((curr, "TitlePlaceholder"))
                        curr_tokens = curr_tokens[matched_count:]
                        found = True
                        break
                
                if not found:
                     if len(path) == 1:
                         # We are still at root and found no child match.
                         # Maybe current token is part of Index Title?
                         # Skip 1 token and retry
                         curr_tokens = curr_tokens[1:]
                         # Continue loop to try again
                         continue
                     
                     # Check default
                     def_child = next((c for c in curr["nodes"] if c.get("default")), None)
                     if def_child:
                         curr = def_child
                         path.append((curr, ""))
                         pass
                     else:
                         # No match, and not root. Stop.
                         # Maybe we reached JaggedArray indices?
                         break
            else:
                break
        
        return path

    @staticmethod
    def _drill_to_last_leaf(node: Dict[str, Any]) -> List[str]:
        """
        Depth-first search to find the LAST leaf node.
        Used for get_prev_section_ref.
        """
        parts = []
        title = next((t["text"] for t in node.get("titles", []) if t.get("primary") and t.get("lang") == "en"), node.get("key"))
        
        if not node.get("default"):
            parts.append(title)
        
        if "nodes" in node and node["nodes"]:
            # Recurse into LAST child
            child_parts = ComplexTextNavigator._drill_to_last_leaf(node["nodes"][-1])
            parts.extend(child_parts)
            
        return parts

    @staticmethod
    def _drill_to_first_leaf(node: Dict[str, Any]) -> List[str]:
        """
        Depth-first search to find the first leaf node (JaggedArray).
        Returns the list of Titles to append to the Ref.
        """
        parts = []
        
        # Determine title for this node
        # If it's the root of drill (sibling), we assume calling function handles its title?
        # No, recursive.
        
        # We need the EN title.
        title = next((t["text"] for t in node.get("titles", []) if t.get("primary") and t.get("lang") == "en"), node.get("key"))
        
        if node.get("default"):
            # Default nodes don't add title
            pass
        else:
            parts.append(title)
        
        if "nodes" in node and node["nodes"]:
            # Recurse into first child
            child_parts = ComplexTextNavigator._drill_to_first_leaf(node["nodes"][0])
            parts.extend(child_parts)
            
        return parts

    @staticmethod
    def _traverse_tokens(node: Dict[str, Any], content: Any, tokens: List[str], he_ref_parts: List[str], parsed_ref: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursive traversal using token list.
        Greedily matches tokens against child node titles.
        """
        # Base case: No more tokens
        if not tokens:
            # We are at the target node (or close to it).
            
            # Construct HeRef
            full_he_ref = ", ".join([p for p in he_ref_parts if p])
            
            # If leaf (JaggedArrayNode), return content
            if node.get("nodeType") == "JaggedArrayNode":
                return {
                    "content": content,
                    "heRef": full_he_ref,
                    "node": node,
                    "is_complex": True,
                    "full_content": content,
                    "current_index": 0 
                }
            
            # If SchemaNode, check for default child
            if "nodes" in node:
                for child in node["nodes"]:
                    if child.get("default"):
                         return ComplexTextNavigator._traverse_tokens(
                             child, 
                             content.get("default", content) if isinstance(content, dict) else content, # Flattened default? 
                             # Note: Sefaria structure usually implies default child content is at same level or under specific key? 
                             # Actually usually default child means the parent dictionary DOES NOT have keys, it just has the content of the default child.
                             # But in MongoDB it's stored under 'default' key if siblings exist, or just as the content if implicit?
                             # Let's assume content acts as the child content.
                             tokens, 
                             he_ref_parts, 
                             parsed_ref
                        )
            
            # If we reached a SchemaNode with children but no default, aggregate all child content
            # This handles cases like "Machzor, Maariv" where Maariv is an organizational node
            if "nodes" in node and isinstance(content, dict):
                aggregated_content = []
                for child in node["nodes"]:
                    child_key = child.get("key")
                    if child_key and child_key in content:
                        child_content = content[child_key]
                        # If child is a JaggedArrayNode, its content should be a list
                        if isinstance(child_content, list):
                            aggregated_content.extend(child_content)
                        elif isinstance(child_content, str):
                            aggregated_content.append(child_content)
                        # If child is also a SchemaNode with more structure, skip for now
                
                if aggregated_content:
                    return {
                        "content": aggregated_content,
                        "heRef": full_he_ref,
                        "node": node,
                        "is_complex": True,
                        "full_content": aggregated_content,
                        "current_index": 0
                    }
            
            return {"content": None, "heRef": full_he_ref}

        # Recursive Step: Try to match tokens to a child node
        if "nodes" in node:
            for child in node["nodes"]:
                matched_tokens_count = 0
                matched_title_he = None
                
                # Check titles
                child_titles = child.get("titles", [])
                
                # Check numeric key matching (e.g. "Mitzvah 1")? 
                # No, strict title matching first.
                
                for t in child_titles:
                    t_text = t["text"]
                    if t.get("lang") == "en":
                        t_tokens = ReferenceNavigator.tokenize_ref(t_text)
                        
                        # Check if tokens start with t_tokens
                        if len(tokens) >= len(t_tokens):
                            match = True
                            for i in range(len(t_tokens)):
                                if tokens[i].lower() != t_tokens[i].lower():
                                    match = False
                                    break
                            
                            if match:
                                # Found a match!
                                # Prefer longer matches? (Greedy)
                                # For now take first match.
                                matched_tokens_count = len(t_tokens)
                                break
                
                # Also check 'key'
                if matched_tokens_count == 0:
                     key = child.get("key", "")
                     key_tokens = ReferenceNavigator.tokenize_ref(key)
                     if len(tokens) >= len(key_tokens):
                            match = True
                            for i in range(len(key_tokens)):
                                if tokens[i].lower() != key_tokens[i].lower():
                                    match = False
                                    break
                            if match:
                                matched_tokens_count = len(key_tokens)
                
                if matched_tokens_count > 0:
                    # Determine HeTitle
                    child_he_title = next((t["text"] for t in child_titles if t.get("primary") and t.get("lang") == "he"), child.get("heTitle", ""))
                    new_he_ref_parts = he_ref_parts + ([child_he_title] if child_he_title else [])
                    
                    # Recurse
                    # Content: usually under 'key' in the dict, unless it's a list.
                    child_key = child.get("key")
                    new_content = None
                    if isinstance(content, dict):
                        new_content = content.get(child_key)
                    elif isinstance(content, list):
                        # Should not happen for SchemaNode -> SchemaNode? 
                        # Unless Mixed?
                        pass
                    
                    if new_content is not None or "nodes" in child: # Allow navigation even if content missing (might be deeper)
                         return ComplexTextNavigator._traverse_tokens(
                             child,
                             new_content,
                             tokens[matched_tokens_count:],
                             new_he_ref_parts,
                             parsed_ref
                         )
        
        # If no child matched, check if current node is JaggedArrayNode
        # If so, remaining tokens are indices/sections.
        if node.get("nodeType") == "JaggedArrayNode":
            # Consume tokens as indices
             return ComplexTextNavigator._handle_jagged_array_tokens(node, content, tokens, he_ref_parts)
             
        # Check default child if no match found
        if "nodes" in node:
             def_child = next((c for c in node["nodes"] if c.get("default")), None)
             if def_child:
                  # Enter default child with ALL tokens intact (since we didn't match them)
                  return ComplexTextNavigator._traverse_tokens(
                         def_child,
                         content.get("default") if isinstance(content, dict) else content, # Careful with content path
                         tokens,
                         he_ref_parts,
                         parsed_ref
                    )

        return {"content": None, "heRef": ", ".join([p for p in he_ref_parts if p])}

    @staticmethod
    def _handle_jagged_array_tokens(node: Dict[str, Any], content: Any, tokens: List[str], he_ref_parts: List[str]) -> Dict[str, Any]:
        """
        Handles navigation within a JaggedArrayNode using tokens.
        Tokens represent indices (e.g. ["1", "5"]).
        """
        current_content = content
        traversed_indices = []
        is_talmud = False
        addr_types = node.get("addressTypes") or []
        for t in addr_types:
            if isinstance(t, str) and t.lower() == "talmud":
                is_talmud = True
                break
        
        i = 0
        while i < len(tokens):
            if not isinstance(current_content, list):
                break
            token = tokens[i]
            if is_talmud:
                m = re.match(r"(?i)(\d+)([ab])$", token)
                if m:
                    daf_num = int(m.group(1))
                    side = m.group(2).lower()
                    idx = (daf_num - 1) * 2 + (0 if side == "a" else 1)
                    if 0 <= idx < len(current_content):
                        current_content = current_content[idx]
                        traversed_indices.append(idx)
                        i += 1
                        if i < len(tokens) and tokens[i].isdigit() and isinstance(current_content, list):
                            line_idx = int(tokens[i]) - 1
                            if 0 <= line_idx < len(current_content):
                                current_content = current_content[line_idx]
                                traversed_indices.append(line_idx)
                            i += 1
                        continue
                    break
            if token.isdigit():
                idx = int(token) - 1
                if 0 <= idx < len(current_content):
                    current_content = current_content[idx]
                    traversed_indices.append(idx)
                    i += 1
                    continue
                break
            break
        
        base_ref = ", ".join([p for p in he_ref_parts if p])
        final_he_ref = base_ref
        
        if traversed_indices:
            if is_talmud:
                daf_idx = traversed_indices[0]
                daf_num = (daf_idx // 2) + 1
                side = "a" if daf_idx % 2 == 0 else "b"
                he_daf = ComplexTextNavigator.encode_hebrew_numeral(daf_num)
                suffix = "." if side == "a" else ":"
                final_he_ref = f"{base_ref} {he_daf}{suffix}".strip()
                if len(traversed_indices) > 1:
                    line_num = traversed_indices[1] + 1
                    final_he_ref = f"{final_he_ref} {ComplexTextNavigator.encode_hebrew_numeral(line_num)}"
            else:
                he_nums = [ComplexTextNavigator.encode_hebrew_numeral(i + 1) for i in traversed_indices]
                final_he_ref = f"{base_ref} " + ":".join(he_nums) if base_ref else ":".join(he_nums)

        return {
            "content": current_content,
            "heRef": final_he_ref,
            "node": node,
            "is_complex": True,
            "full_content": content,
            "current_index": traversed_indices[0] if traversed_indices else 0,
            "base_he_ref": base_ref,
        }


    @staticmethod
    def is_content_empty(content: Any) -> bool:
        """Check if content is empty (recursively for nested structures)."""
        if content is None:
            return True
        if isinstance(content, str):
            return not content.strip()
        if isinstance(content, list):
            # Check if list is empty or all items are empty
            if not content:
                return True
            return all(ComplexTextNavigator.is_content_empty(item) for item in content)
        if isinstance(content, dict):
            # Check if all values are empty
            return all(ComplexTextNavigator.is_content_empty(v) for v in content.values())
        return False
