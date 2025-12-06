import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException

from app.db.connection import MongoDatabase
from app.db.models.sefaria import Text


@dataclass
class RangeContext:
    raw: Optional[Dict[str, str]]
    start: Optional[Dict[str, Any]]
    end: Optional[Dict[str, Any]]


class ReferenceNavigator:
    # Regex to capture the numeric part at the end of a reference
    # Group 1: Chapter number
    # Group 2: Optional verse number
    # Group 3: Daf number
    # Group 4: Daf side (a/b)
    # Group 5: Optional line number
    NUMERIC_PART_PATTERN = re.compile(r"(?:(\d+)(?::(\d+))?)|(?:(\d+)([ab])(?::(\d+))?)$", re.IGNORECASE)

    @classmethod
    def parse_ref(cls, ref: str) -> Dict[str, Any]:
        """Parses Sefaria references into structured metadata, handling multi-part titles."""
        original_ref = ref
        parsed_data: Dict[str, Any] = {"index": ref} # Default to full ref as index

        # Try to match the numeric part at the end of the reference
        match = cls.NUMERIC_PART_PATTERN.search(ref)

        if match:
            # Extract numeric components
            chapter_num = match.group(1)
            verse_num = match.group(2)
            daf_num = match.group(3)
            daf_side = match.group(4)
            line_num = match.group(5)

            # Determine the type of reference and extract components
            if daf_num and daf_side: # Talmudic reference
                parsed_data["daf_num"] = int(daf_num)
                parsed_data["side"] = daf_side.lower()
                parsed_data["daf"] = f"{parsed_data['daf_num']}{parsed_data['side']}"
                if line_num:
                    parsed_data["line"] = int(line_num)
                
                # The index title is everything before the daf part
                index_title_end_pos = match.start(3) if match.start(3) != -1 else match.start(4)
                index_title = ref[:index_title_end_pos].strip()
                parsed_data["index"] = index_title if index_title else original_ref

            elif chapter_num: # Chapter/Verse reference
                parsed_data["chapter"] = int(chapter_num)
                if verse_num:
                    parsed_data["verse"] = int(verse_num)
                
                # The index title is everything before the chapter part
                index_title_end_pos = match.start(1) if match.start(1) != -1 else match.start(2)
                index_title = ref[:index_title_end_pos].strip()
                parsed_data["index"] = index_title if index_title else original_ref
            
            
            # Clean up the index title if it ends with a comma or colon
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
            # For Talmud, index 0 corresponds to 2a, index 1 to 2b, etc.
            # So, daf_num = (index // 2) + 2
            # And side = 'a' if index % 2 == 0 else 'b'
            daf_num = (index // 2) + 2
            side = 'a' if index % 2 == 0 else 'b'
            return f"{index_title} {daf_num}{side}"
        else:
            # For chapter-based texts, index 0 corresponds to chapter 1, etc.
            return f"{index_title} {index + 1}"

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
        
        # Try to match and strip Index Title from tokens
        # We assume the ref starts with the Index Title (e.g. "Sefer Mitzvot Gadol")
        # We need to find how many tokens match the index title.
        index_title_tokens = ReferenceNavigator.tokenize_ref(text_data.get("title", ""))
        
        # Optimization: Check if tokens start with index_title_tokens
        current_tokens = tokens
        if len(tokens) >= len(index_title_tokens):
            match = True
            for i in range(len(index_title_tokens)):
                if tokens[i].lower() != index_title_tokens[i].lower():
                    match = False
                    break
            if match:
                current_tokens = tokens[len(index_title_tokens):]
        
        # Start traversal from root
        current_node = schema
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
        
        # Mapping for hundreds, tens, ones
        ones = ["", "א", "ב", "ג", "ד", "ה", "ו", "ז", "ח", "ט"]
        tens = ["", "י", "כ", "ל", "מ", "נ", "ס", "ע", "פ", "צ"]
        hundreds = ["", "ק", "ר", "ש", "ת"]
        
        result = ""
        
        # Hundreds
        h = (n // 100) % 10
        if 1 <= h <= 4:
            result += hundreds[h]
        elif h >= 5:
            # Simplified fallback for >400
            for _ in range(h):
                result += "ק" 
            
        # Tens
        t = (n // 10) % 10
        # Ones
        o = n % 10
        
        # Special cases 15 (Tet-Vav) and 16 (Tet-Zayin)
        if t == 1 and o == 5:
            result += "טו"
        elif t == 1 and o == 6:
            result += "טז"
        else:
            result += tens[t]
            result += ones[o]
            
        # Add Geresh or Gershayim
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
                if not prev_sibling.get("default"):
                    prev_sibling_title = next((t["text"] for t in prev_sibling.get("titles", []) if t.get("primary") and t.get("lang") == "en"), prev_sibling.get("key"))
                    ref_builder.append(prev_sibling_title)
                
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
                if not next_sibling.get("default"):
                     next_sibling_title = next((t["text"] for t in next_sibling.get("titles", []) if t.get("primary") and t.get("lang") == "en"), next_sibling.get("key"))
                     ref_builder.append(next_sibling_title)
                
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
                        if t.get("lang") == "en":
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
        current_he_ref_parts = he_ref_parts[:]
        traversed_indices = []
        
        # Iterate tokens and drill down
        for token in tokens:
            if not isinstance(current_content, list):
                break # Cannot drill further
            
            # Parse token as integer
            try:
                # Handle "2a", "2b" for Talmud? 
                # Or just int.
                # Basic Integer
                if token.isdigit():
                    idx = int(token) - 1
                else:
                    # Attempt Talmud logic or ignore?
                    # For now assume digit
                    break 
                    
                if 0 <= idx < len(current_content):
                    current_content = current_content[idx]
                    traversed_indices.append(idx)
                    
                    # Append HeRef 
                    he_num = ComplexTextNavigator.encode_hebrew_numeral(idx + 1)
                    # Modify the LAST part of he_ref? 
                    # Sefaria style: "Title, Section" -> "Title, Section HeNum"
                    # But here we are Drilling DOWN.
                    # Base HeRef is [Title, NodeTitle].
                    # We append "HeNum".
                    # If deeper: "Title, NodeTitle HeNum:HeNum"
                    # Let's accumulate numbers.
                    
                    # Actually, we usually want to return the LAST he_ref logic.
                    # Let's just append to parts.
                    # But wait, we want "Siman Aleph" not "Siman, Aleph".
                    # So we modify the last part? 
                    # Or we just maintain a string?
                    pass 
                else:
                     break
            except ValueError:
                break
        
        # Reconstruct HeRef
        # We need to know where to append numbers.
        # If we traversed indices, append them to the last he_ref_part?
        base_ref = ", ".join([p for p in he_ref_parts if p])
        final_he_ref = base_ref
        
        if traversed_indices:
             he_nums = [ComplexTextNavigator.encode_hebrew_numeral(i+1) for i in traversed_indices]
             # Format: "BaseRef Num:Num"
             final_he_ref += " " + ":".join(he_nums)

        return {
            "content": current_content, # Sliced content
            "heRef": final_he_ref,
            "node": node,
            "is_complex": True,
            "full_content": content, # Return ROOT content of this node for pagination neighbors
            "current_index": traversed_indices[0] if traversed_indices else 0, # Top level index
             # Note: If we drilled deep (Depth 3), this index is for the top level of this node.
             # Pagination logic usually works on top level of the leaf node.
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



class TextService:
    @staticmethod
    def _normalize_chapter_data(chapter_data):
        if isinstance(chapter_data, dict):
            if 'default' in chapter_data:
                return chapter_data['default']
            return list(chapter_data.values())[0] if chapter_data else []
        return chapter_data if isinstance(chapter_data, list) else []
    
    @staticmethod
    def _has_header_in_first_segment(doc_check):
        chapter_data_check = doc_check.get("chapter", [])
        chapter_data_check = TextService._normalize_chapter_data(chapter_data_check)
        if isinstance(chapter_data_check, list) and len(chapter_data_check) > 0:
            first_chapter = chapter_data_check[0]
            if isinstance(first_chapter, list) and len(first_chapter) > 0:
                first_seg = str(first_chapter[0])
                return "<b>" in first_seg and ("דין" in first_seg[:200] or "ובו" in first_seg[:200])
        return False
    
    @staticmethod
    async def _find_best_document(db, index_title: str, preferred_version: Optional[str] = None):
        """Find best text document, optionally preferring a specific version."""
        # If a preferred version is specified, try to find it first
        if preferred_version:
            doc = await db.texts.find_one({
                "title": {"$regex": f"^{index_title}$", "$options": "i"},
                "versionTitle": preferred_version,
                "language": "he"
            })
            if doc:
                return doc
        
        # Otherwise, fall back to existing logic
        all_he_docs = await db.texts.find({
            "title": {"$regex": f"^{index_title}$", "$options": "i"},
            "language": "he"
        }).to_list(length=None)
        
        if all_he_docs:
            # Filter versions with priority field and select highest priority
            versions_with_priority = [v for v in all_he_docs if "priority" in v and v["priority"] is not None]
            
            if versions_with_priority:
                # Select the version with highest priority
                best_doc = max(versions_with_priority, key=lambda v: v["priority"])
                return best_doc
            
            # Fallback: check for headers in first segment
            for candidate_doc in all_he_docs:
                if TextService._has_header_in_first_segment(candidate_doc):
                    return candidate_doc
            if all_he_docs:
                return all_he_docs[0]

        
        doc = await db.texts.find_one({"title": index_title, "language": "he"})
        if doc:
            return doc
        
        doc = await db.texts.find_one({
            "title": {"$regex": f"^{index_title}$", "$options": "i"},
            "language": "he"
        })
        if doc:
            return doc
        
        doc = await db.texts.find_one({"title": index_title})
        if doc:
            return doc
        
        return await db.texts.find_one({"title": {"$regex": f"^{index_title}$", "$options": "i"}})
    
    @staticmethod
    async def fetch_page_data(db, page_ref: str, range_ctx: RangeContext, is_main_page: bool = False, preferred_version: Optional[str] = None) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """Loads page content along with highlight metadata."""
        parsed = ReferenceNavigator.parse_ref(page_ref)
        index_title = parsed["index"]
        doc = await TextService._find_best_document(db, index_title, preferred_version)
        if not doc:
            return None
        chapter_data = doc.get("chapter", [])
        chapter_data = TextService._normalize_chapter_data(chapter_data)
        page_result: Dict[str, Any] = {
            "ref": page_ref,
            "segments": [],
            "highlight_index": None,
            "highlight_indices": []
        }
        if "daf" in parsed:
            processed = TextService._handle_daf(parsed, chapter_data, page_result, range_ctx, is_main_page)
            if processed is None:
                return None
            return processed, doc
        if "chapter" in parsed and parsed["chapter"] is not None:
            processed = TextService._handle_chapter(parsed, chapter_data, page_result, range_ctx, is_main_page)
            if processed is None:
                return None
            return processed, doc
        for chapter in chapter_data:
            if isinstance(chapter, list):
                page_result["segments"].extend(chapter)
            else:
                page_result["segments"].append(chapter)
        return page_result, doc

    @staticmethod
    def _handle_daf(parsed, chapter_data, page_result, range_ctx, is_main_page):
        """Processes daf-based pagination blocks."""
        daf_num = parsed["daf_num"]
        side = parsed["side"]
        line = parsed.get("line")
        daf_index = (daf_num - 1) * 2 + (0 if side == 'a' else 1)
        if daf_index >= len(chapter_data):
            return None
        daf_content = chapter_data[daf_index]
        if isinstance(daf_content, list):
            page_result["segments"] = daf_content
            if is_main_page and line is not None and not range_ctx.raw:
                line_index = line - 1
                if line_index < len(daf_content):
                    page_result["highlight_index"] = line_index
                    page_result["highlight_indices"] = [line_index]
            if range_ctx.raw:
                for i in range(len(daf_content)):
                    if ReferenceNavigator.is_in_range(i, parsed, range_ctx):
                        page_result["highlight_indices"].append(i)
                if page_result["highlight_indices"]:
                    page_result["highlight_index"] = page_result["highlight_indices"][0]
        else:
            page_result["segments"] = [daf_content]
            if is_main_page:
                page_result["highlight_index"] = 0
                page_result["highlight_indices"] = [0]
        return page_result

    @staticmethod
    def _handle_chapter(parsed, chapter_data, page_result, range_ctx, is_main_page):
        """Processes chapter-based pagination blocks."""
        chapter_num = parsed["chapter"] - 1
        if chapter_num >= len(chapter_data):
            return None
        chapter_content = chapter_data[chapter_num]
        if isinstance(chapter_content, list):
            page_result["segments"] = chapter_content
            if is_main_page and "verse" in parsed and parsed["verse"] is not None and not range_ctx.raw:
                verse_num = parsed["verse"] - 1
                if verse_num < len(chapter_content):
                    page_result["highlight_index"] = verse_num
                    page_result["highlight_indices"] = [verse_num]
            if range_ctx.raw:
                for i in range(len(chapter_content)):
                    if ReferenceNavigator.is_in_range(i, parsed, range_ctx):
                        page_result["highlight_indices"].append(i)
                if page_result["highlight_indices"]:
                    page_result["highlight_index"] = page_result["highlight_indices"][0]
        else:
            page_result["segments"] = [chapter_content]
            if is_main_page:
                page_result["highlight_index"] = 0
                page_result["highlight_indices"] = [0]
        return page_result


class TextEndpoints:
    router = APIRouter(tags=["texts"])

    @staticmethod
    @router.get("/texts/{ref}")
    async def get_text(ref: str):
        """Returns the stored text document for the requested ref."""
        db = MongoDatabase.get_db()
        doc = await db.texts.find_one({"title": ref})
        if not doc:
            doc = await db.texts.find_one({"title": {"$regex": f"^{ref}$", "$options": "i"}})
        if doc:
            return Text(**doc)
        raise HTTPException(status_code=404, detail="Text not found")

    @staticmethod
    @router.get("/api/source/{ref:path}")
    async def get_source_text(ref: str, pages_before: int = 0, pages_after: int = 0):
        """Returns rich source payloads with optional pagination, supporting both simple and complex texts."""
        db = MongoDatabase.get_db()
        range_info = ReferenceNavigator.parse_range_ref(ref)
        primary_ref = range_info["start"] if range_info else ref
        
        # Parse the primary ref to get index title
        parsed = ReferenceNavigator.parse_ref(primary_ref)
        index_title = parsed["index"]
        
        # Try to get the best version from the index in the database
        index_doc = await db.index.find_one({"title": index_title})
        
        preferred_version = None
        
        doc = await TextService._find_best_document(db, index_title, preferred_version)
        
        # If not found, and ref has commas, try the first part as title (for complex refs)
        if not doc and "," in primary_ref:
            base_title = primary_ref.split(",")[0].strip()
            # Try to find index doc for base title
            if not index_doc:
                index_doc = await db.index.find_one({"title": base_title})
            
            doc = await TextService._find_best_document(db, base_title, preferred_version)
            if doc:
                index_title = base_title
        
        if not doc:
            raise HTTPException(status_code=404, detail=f"Reference '{ref}' not found")
        
        # We need the Index Schema for complex navigation
        # Fallback to empty dict if schema not found
        schema = index_doc.get("schema", {}) if index_doc else {}

        # Use ComplexTextNavigator to get the content
        nav_result = ComplexTextNavigator.navigate_to_section(doc, schema, primary_ref, index_doc)
        content = nav_result.get("content")
        he_ref = nav_result.get("heRef") or doc.get("heRef") or doc.get("heTitle")

        if content is None or ComplexTextNavigator.is_content_empty(content):
            raise HTTPException(status_code=404, detail=f"Content not found for reference '{ref}' (section may be empty)")
        
        # Determine if this is Talmud
        is_talmud = "daf" in parsed
        
        # Handle Complex Structure result
        if nav_result.get("is_complex") and not nav_result.get("force_single_page"):
             
             # If we have full_content and indices, we can support pagination
             full_content = nav_result.get("full_content")
             current_idx = nav_result.get("current_index")
             
             if full_content and current_idx is not None and isinstance(full_content, list):
                 # We are in a navigable list (JaggedArray)
                 
                 # Logic to construct Base Ref (strip the last number)
                 base_ref = primary_ref
                 import re
                 match = re.search(r"(\d+)$", primary_ref)
                 if match:
                     base_ref = primary_ref[:match.start()].strip().rstrip(',')
                 
                 # Identify indices to fetch
                 total_len = len(full_content)
                 indices_to_fetch = []
                 # Before
                 scan = current_idx - 1
                 count = 0
                 while scan >= 0 and count < pages_before:
                     if not ComplexTextNavigator.is_content_empty(full_content[scan]):
                         indices_to_fetch.insert(0, scan)
                         count += 1
                     scan -= 1
                 can_load_top = (scan >= 0)
                 extra_pages_before = []
                 if not can_load_top:
                     # Check for previous section (Inter-Node Backward Pagination)
                     prev_ref = ComplexTextNavigator.get_prev_section_ref(doc.get("title", ""), schema, primary_ref)
                     if prev_ref:
                         can_load_top = True
                         if pages_before > count: # fetching more than we found in current
                             remaining_before = pages_before - count
                             prev_nav_result = ComplexTextNavigator.navigate_to_section(doc, schema, prev_ref, index_doc)
                             if prev_nav_result.get("content") and prev_nav_result.get("is_complex"):
                                 prev_full = prev_nav_result.get("full_content") 
                                 if not prev_full and isinstance(prev_nav_result.get("content"), list):
                                      prev_full = prev_nav_result.get("content")
                                 
                                 # For Depth-1 Previous Node:
                                 prev_node = prev_nav_result.get("node", {})
                                 if prev_node.get("depth") == 1:
                                     prev_full_heref = prev_nav_result.get("heRef") or prev_nav_result.get("base_he_ref")
                                     extra_pages_before.insert(0, {
                                        "ref": prev_ref,
                                        "he_ref": ComplexTextNavigator.strip_book_title_from_heref(prev_full_heref),
                                        "full_he_ref": prev_full_heref, # Full ref for header updates
                                        "segments": prev_full, 
                                        "highlight_index": None,
                                        "highlight_indices": []
                                    })
                                 else:
                                     prev_he_ref = prev_nav_result.get("heRef") or prev_nav_result.get("base_he_ref")
                                     if prev_full:
                                         # We want the LAST pages of the previous section
                                         # e.g. Mitzvah 2:1, 2:2. We want 2:2 if we scroll up from Mitzvah 3
                                         len_prev = len(prev_full)
                                         start_slice = max(0, len_prev - remaining_before)
                                         for k in range(start_slice, len_prev):
                                             seg_content = prev_full[k]
                                             seg_ref = f"{prev_ref}:{k+1}"
                                             full_seg_he_ref = prev_he_ref 
                                             if full_seg_he_ref:
                                                  full_seg_he_ref += f" {ComplexTextNavigator.encode_hebrew_numeral(k+1)}"
                                             seg_he_ref = ComplexTextNavigator.strip_book_title_from_heref(full_seg_he_ref)

                                             extra_pages_before.append({
                                                "ref": seg_ref,
                                                "he_ref": seg_he_ref,
                                                "full_he_ref": full_seg_he_ref, # Full ref for header updates
                                                "segments": [seg_content] if isinstance(seg_content, str) else seg_content,
                                                "highlight_index": None,
                                                "highlight_indices": []
                                            })
                 # Current
                 indices_to_fetch.append(current_idx)
                 # After
                 scan = current_idx + 1
                 count = 0
                 while scan < total_len and count < pages_after:
                     if not ComplexTextNavigator.is_content_empty(full_content[scan]):
                         indices_to_fetch.append(scan)
                         count += 1
                     scan += 1
                 can_load_bottom = (scan < total_len)

                 current_node_depth = nav_result.get("node", {}).get("depth")

                 # Build Pages (Moved UP)
                 pages = []
                 main_page_index = 0
                 
                 base_he_ref = nav_result.get("base_he_ref") or nav_result.get("heRef")
                 # Store full heRef for main header BEFORE stripping
                 full_main_heref = base_he_ref

                 if current_node_depth == 1:
                     # FORCE SINGLE PAGE for Depth 1 (e.g. Remazim)
                     # Bundle all content into one page.
                     
                     # Check if we need to prepend previous sections (extra_pages_before)
                     # But for the MAIN content, it's one block.
                     
                     page_ref = base_ref if not any(c.isdigit() for c in base_ref.split(" ")[-1]) else primary_ref 
                     # Better: use primary_ref directly? Or nav_result ref?
                     # nav_result.get("ref") is usually clean.
                     page_ref = nav_result.get("ref", primary_ref)

                     page_res = {
                        "ref": page_ref,
                        "he_ref": ComplexTextNavigator.strip_book_title_from_heref(base_he_ref), # Strip book title for page display
                        "full_he_ref": base_he_ref, # Full ref for header updates
                        "segments": full_content,
                        "highlight_index": current_idx if current_idx != 0 else None, # Only if we jumped to specific segment
                        "highlight_indices": []
                     }
                     pages.append(page_res)
                     
                     # For Depth 1, 'can_load_bottom' based on internal scanning is always False (we showed all).
                     # So we rely on the check below for 'next_ref'.
                     can_load_bottom = False 
                     
                     # Key Fix: Since we bundled all segments into 1 page, we haven't 'used up' our pages_after budget 
                     # on individual segments. We should reset count to allow loading the next section.
                     count = 0

                 else:
                     # Original Depth > 1 logic (Pagination by index)
                     for i, idx in enumerate(indices_to_fetch):
                         if idx == current_idx:
                             main_page_index = i
                         
                         # Construct Ref
                         page_ref = f"{base_ref} {idx + 1}".strip()
                         
                         # Construct heRef
                         if base_he_ref:
                             he_num = ComplexTextNavigator.encode_hebrew_numeral(idx + 1)
                             full_page_he_ref = f"{base_he_ref} {he_num}"
                             page_he_ref = ComplexTextNavigator.strip_book_title_from_heref(full_page_he_ref)
                             # Update full_main_heref for the main page
                             if idx == current_idx:
                                 full_main_heref = full_page_he_ref
                         else:
                             page_he_ref = nav_result.get("heRef")
                         
                         # Get content
                         seg_content = full_content[idx]
                         segments = seg_content if isinstance(seg_content, list) else [seg_content]
                         
                         page_res = {
                            "ref": page_ref,
                            "he_ref": page_he_ref,
                            "full_he_ref": full_page_he_ref if base_he_ref else None, # Full ref for header updates
                            "segments": segments,
                            "highlight_index": None,
                            "highlight_indices": []
                        }
                         
                         # Apply highlighting only to main page if requested
                         if idx == current_idx:
                             if "verse" in parsed and parsed["verse"]:
                                 v_idx = parsed["verse"] - 1
                                 if 0 <= v_idx < len(segments):
                                     page_res["highlight_index"] = v_idx
                                     page_res["highlight_indices"] = [v_idx]
                         
                         pages.append(page_res)

                 if not can_load_bottom:
                    # Check if there is a next section (Inter-Node Pagination)
                    next_ref = ComplexTextNavigator.get_next_section_ref(doc.get("title", ""), schema, primary_ref)
                    if next_ref:
                         can_load_bottom = True
                         
                         # If client requested more pages, we should actually fetch that next ref
                         if pages_after > count: # 'count' is pages collected from current section

                             # Recursive call or new navigator?
                             # We can just fetch it as a separate get_source_text call?
                             # Ideally we want to append it to 'pages'.
                             # For simplicity, we just navigate to it and process it.
                             
                             # We need to fetch it.
                             # Reuse the same logic?
                             # Let's do a recursive-like fetch but be careful about infinite loops.
                             # Actually, we can just call ComplexTextNavigator.navigate_to_section again with next_ref
                             next_nav_result = ComplexTextNavigator.navigate_to_section(doc, schema, next_ref, index_doc)
                             if next_nav_result.get("content") and next_nav_result.get("is_complex"):
                                 # We need to process this new result into pages.
                                 # Assuming next section starts at index 0.
                                 next_full = next_nav_result.get("full_content") 
                                 next_he_ref = next_nav_result.get("heRef") or next_nav_result.get("base_he_ref")
                                 
                                 # This logic is repeating the page construction.
                                 # Maybe we loop?
                                 
                                 # For MVP: Just append the FIRST page of the next section.
                                 if isinstance(next_full, list) and next_full:
                                     # Get first segment
                                     # We need to handle pagination in the next section too if we want >1 pages from it.
                                     # Let's just grab the first chunk.
                                     next_idx = 0
                                     # Construct Ref
                                     base_next_ref = next_ref # assuming next_ref targets the JaggedArray
                                     
                                     # Wait, get_next_section_ref returns the Ref to the JaggedArray.
                                     # If it's "Positive Commandments 1", next_full is the list of content for that mitzvah.
                                     # If it's "Remazim", next_full is list of segments.
                                     # We take slice.
                                     remaining_pages = pages_after - count
                                     slice_end = min(len(next_full), remaining_pages) 
                                     
                                     # Check Depth of next section
                                     next_node = next_nav_result.get("node", {})
                                     next_depth = next_node.get("depth")

                                     if next_depth == 1:
                                          # Bundle entire section as ONE page
                                          pages.append({
                                             "ref": next_ref,
                                             "he_ref": ComplexTextNavigator.strip_book_title_from_heref(next_he_ref),
                                             "full_he_ref": next_he_ref, # Full ref for header updates
                                             "segments": next_full, # All segments
                                             "highlight_index": None,
                                             "highlight_indices": []
                                         })
                                         
                                          # Check for section AFTER this next one to allow further scrolling
                                          next_next_ref = ComplexTextNavigator.get_next_section_ref(doc.get("title", ""), schema, next_ref)
                                          if next_next_ref:
                                              can_load_bottom = True
                                          else:
                                              can_load_bottom = False
                                     else:
                                         # Depth > 1 logic (Pagination by index)
                                         for k in range(slice_end):
                                             seg_content = next_full[k]
                                             
                                             # Construct segment ref
                                             seg_ref = f"{next_ref}:{k+1}"
                                             
                                             # Hebrew Ref
                                             full_seg_he_ref = next_he_ref
                                             if full_seg_he_ref:
                                                  full_seg_he_ref += f" {ComplexTextNavigator.encode_hebrew_numeral(k+1)}"
                                             seg_he_ref = ComplexTextNavigator.strip_book_title_from_heref(full_seg_he_ref)

                                             pages.append({
                                                "ref": seg_ref,
                                                "he_ref": seg_he_ref,
                                                "full_he_ref": full_seg_he_ref, # Full ref for header updates
                                                "segments": [seg_content] if isinstance(seg_content, str) else seg_content,
                                                "highlight_index": None,
                                                "highlight_indices": []
                                            })
                                         
                                         # If we have more segments in THIS section we didn't show
                                         if len(next_full) > slice_end:
                                             can_load_bottom = True
                                         else:
                                             # Successfully exhausted NEXT section. Check for subsequent section.
                                             next_next_ref = ComplexTextNavigator.get_next_section_ref(doc.get("title", ""), schema, next_ref)
                                             if next_next_ref:
                                                  can_load_bottom = True
                 
                 # Combine pages: [previous_section_pages] + [current_section_pages] + [next_section_pages (appended in loop)]
                 # Wait, 'pages' above currently has next section pages appended to it during the loop if I merged logics?
                 # No, the loop logic for current section and next section seems to be:
                 # 1. Fetch current indices
                 # 2. Append next section logic... wait, where is next section logic? 
                 # Ah, it was in the "indices_to_fetch" logic? No, separate block.
                 
                 # Let's check below.
                 # "pages" assumes standard jagged array pagination.
                 # "extra_pages_before" is what we just built.
                 
                 # Need to prepend extra_pages_before
                 if extra_pages_before:
                     pages = extra_pages_before + pages
                     main_page_index += len(extra_pages_before)
                 
                 # Use the full heRef for the main header (not the stripped page version)
                 top_level_he_ref = full_main_heref if full_main_heref else doc.get("heTitle")

                 return {
                    "pages": pages,
                    "main_page_index": main_page_index,
                    "index_title": doc.get("title"),
                    "he_title": doc.get("heTitle"),
                    "he_ref": top_level_he_ref,
                    "version_title": doc.get("versionTitle"),
                    "language": doc.get("language"),
                    "can_load_more": {"top": can_load_top, "bottom": can_load_bottom}
                 }

             # Fallback for complex text without pagination context (e.g. root node)
             segments = content if isinstance(content, list) else [content]
             
             page_result = {
                "ref": primary_ref,
                "he_ref": he_ref,
                "segments": segments,
                "highlight_index": None,
                "highlight_indices": []
            }
             
             # TODO: Improve accurate highlighting from parsed numbers
             if "verse" in parsed and parsed["verse"]:
                 v_idx = parsed["verse"] - 1
                 if 0 <= v_idx < len(segments):
                     page_result["highlight_index"] = v_idx
                     page_result["highlight_indices"] = [v_idx]

             can_load_bottom = False
             extra_pages = []
             
             # Check for next section (Inter-Node Pagination)
             next_ref = ComplexTextNavigator.get_next_section_ref(doc.get("title", ""), schema, primary_ref)
             if next_ref:
                 can_load_bottom = True
                 if pages_after > 0:
                     next_nav_result = ComplexTextNavigator.navigate_to_section(doc, schema, next_ref, index_doc)
                     
                     
                     if next_nav_result.get("content") and next_nav_result.get("is_complex"):
                         next_content = next_nav_result.get("content")
                         next_full = next_nav_result.get("full_content") or (next_content if isinstance(next_content, list) else [next_content])
                         next_he_ref = next_nav_result.get("heRef")
                         
                         
                         
                         # Check Depth of next section
                         next_node = next_nav_result.get("node", {})
                         next_depth = next_node.get("depth")
                         


                         if next_depth == 1:
                             # Bundle entire section as ONE page
                             extra_pages.append({
                                "ref": next_ref,
                                "he_ref": ComplexTextNavigator.strip_book_title_from_heref(next_he_ref),
                                "full_he_ref": next_he_ref, # Full ref for header updates
                                "segments": next_full, # All segments
                                "highlight_index": None,
                                "highlight_indices": []
                            })
                            
                             # Check for section AFTER this next one to allow further scrolling
                             next_next_ref = ComplexTextNavigator.get_next_section_ref(doc.get("title", ""), schema, next_ref)
                             if next_next_ref:
                                 can_load_bottom = True
                             else:
                                 can_load_bottom = False
                                 
                         else:
                             # Original logic for Depth 2+ (Pagination by index)
                             remaining_pages = pages_after
                             slice_end = min(len(next_full), remaining_pages)
                             
                             for k in range(slice_end):
                                 seg_content = next_full[k]
                                 # Sefaria convention: NodeRef:SegmentIndex
                                 seg_ref = f"{next_ref}:{k+1}"
                                 
                                 full_seg_he_ref = next_he_ref
                                 if full_seg_he_ref:
                                     he_num = ComplexTextNavigator.encode_hebrew_numeral(k+1)
                                     full_seg_he_ref += f" {he_num}"
                                 seg_he_ref = ComplexTextNavigator.strip_book_title_from_heref(full_seg_he_ref)
                                     
                                 extra_pages.append({
                                    "ref": seg_ref,
                                    "he_ref": seg_he_ref,
                                    "full_he_ref": full_seg_he_ref, # Full ref for header updates
                                    "segments": [seg_content] if isinstance(seg_content, str) else seg_content,
                                    "highlight_index": None,
                                    "highlight_indices": []
                                })
                             
                             # If we have more segments in THIS section we didn't show
                             if len(next_full) > slice_end:
                                 can_load_bottom = True
                             else:
                                 # Successfuly showed all of current section. Check for subsequent section.
                                 next_next_ref = ComplexTextNavigator.get_next_section_ref(doc.get("title", ""), schema, next_ref)
                                 if next_next_ref:
                                      can_load_bottom = True

             return {
                "pages": [page_result] + extra_pages,
                "main_page_index": 0,
                "index_title": doc.get("title"),
                "he_title": doc.get("heTitle"),
                "he_ref": he_ref,
                "version_title": doc.get("versionTitle"),
                "language": doc.get("language"),
                "can_load_more": {"top": False, "bottom": can_load_bottom}
            }

        
        # Simple reference - use existing pagination logic
        # ... (Legacy logic for simple texts follows if not caught by ref, but we mostly use the new one now?)
        # Actually the navigate_to_section handles simple too, but returns raw content.
        # Let's keep the legacy pagination for DAF/Simple Chapters as it works well.
        
        # Re-using legacy logic below for non-complex triggering or fallback:
        # Note: If navigate_to_section returned is_complex=False, it means it's a simple JaggedArray root.
        
        # CRITICAL FIX: If we successfully navigated a COMPLEX text, we should have returned above.
        # If we fell through, it might be because `is_complex` was False (simple text) OR something weird happened.
        # If `nav_result` says complex, we MUST NOT run the legacy list-based logic below on dictionary content.
        if nav_result.get("is_complex"):
             # We already handled complex pagination above or returned single page.
             # If we are here, it means the complex pagination block didn't return?
             # Actually, looking at the code, the complex block returns if conditions met.
             # If not met, it returns a 1-page result.
             # So we should strictly return from the complex block.
             pass 

        chapter_data = doc.get("chapter", [])
        chapter_data = TextService._normalize_chapter_data(chapter_data)
        
        # Determine current linear index
        current_index = -1
        if is_talmud:
            current_index = (parsed["daf_num"] - 1) * 2 + (0 if parsed["side"] == 'a' else 1)
        elif "chapter" in parsed:
            current_index = parsed["chapter"] - 1
        
        if current_index < 0:
            current_index = 0
        
        # Helper to check content
        def has_content(idx):
            if 0 <= idx < len(chapter_data):
                content = chapter_data[idx]
                if isinstance(content, list):
                    return len(content) > 0
                return bool(content)
            return False
        
        # Find indices to fetch
        indices_to_fetch = []
        
        # Pages Before (search backwards for non-empty)
        scan = current_index - 1
        count = 0
        before_indices = []
        while scan >= 0 and count < pages_before:
            if has_content(scan):
                before_indices.append(scan)
                count += 1
            scan -= 1
        
        can_load_top = (scan >= 0)
        indices_to_fetch.extend(reversed(before_indices))
        
        # Current Page (always include, even if empty, to show where user landed)
        if 0 <= current_index < len(chapter_data):
            indices_to_fetch.append(current_index)
        
        # Pages After (search forwards for non-empty)
        scan = current_index + 1
        count = 0
        while scan < len(chapter_data) and count < pages_after:
            if has_content(scan):
                indices_to_fetch.append(scan)
                count += 1
            scan += 1
            
        can_load_bottom = (scan < len(chapter_data))
        
        # Construct Pages
        pages = []
        main_page_index = 0
        
        range_ctx = RangeContext(
            raw=range_info,
            start=ReferenceNavigator.parse_ref(range_info["start"]) if range_info else None,
            end=ReferenceNavigator.parse_ref(range_info["end"]) if range_info else None
        )
        
        for i, idx in enumerate(indices_to_fetch):
            if idx == current_index:
                main_page_index = i
            
            page_ref = ReferenceNavigator.get_ref_from_index(index_title, idx, is_talmud)
            page_parsed = ReferenceNavigator.parse_ref(page_ref)
            
            page_result = {
                "ref": page_ref,
                "he_ref": doc.get("heRef"),
                "segments": [],
                "highlight_index": None,
                "highlight_indices": []
            }
            
            processed = None
            is_main = (idx == current_index)
            ctx = range_ctx if is_main else RangeContext(None, None, None)
            
            if is_talmud:
                processed = TextService._handle_daf(page_parsed, chapter_data, page_result, ctx, is_main)
            else:
                processed = TextService._handle_chapter(page_parsed, chapter_data, page_result, ctx, is_main)
            
            if processed:
                pages.append(processed)
        
        return {
            "pages": pages,
            "main_page_index": main_page_index,
            "index_title": doc.get("title"),
            "he_title": doc.get("heTitle"),
            "version_title": doc.get("versionTitle"),
            "language": doc.get("language"),
            "can_load_more": {"top": can_load_top, "bottom": can_load_bottom}
        }
