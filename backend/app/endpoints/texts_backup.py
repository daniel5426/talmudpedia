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
    talmud_pattern = r"^(.+?)\s+(\d+)([ab])(?::(\d+))?$"
    biblical_pattern = r"^(.+?)\s+(\d+)(?::(\d+))?$"

    @classmethod
    def parse_ref(cls, ref: str) -> Dict[str, Any]:
        """Parses Sefaria references into structured metadata."""
        match = re.match(cls.talmud_pattern, ref, re.IGNORECASE)
        if match:
            index_title = match.group(1)
            daf_num = int(match.group(2))
            side = match.group(3).lower()
            line = int(match.group(4)) if match.group(4) else None
            daf = f"{daf_num}{side}"
            return {"index": index_title, "daf": daf, "daf_num": daf_num, "side": side, "line": line}
        match = re.match(cls.biblical_pattern, ref)
        if match:
            index_title = match.group(1)
            chapter = int(match.group(2))
            verse = int(match.group(3)) if match.group(3) else None
            return {"index": index_title, "chapter": chapter, "verse": verse}
        return {"index": ref}

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
            linear_index = (daf_num - 2) * 2 + (0 if side == 'a' else 1)
            new_linear_index = linear_index + offset
            if new_linear_index < 0:
                return None
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
            daf_num = (index // 2) + 1
            side = 'a' if index % 2 == 0 else 'b'
            return f"{index_title} {daf_num}{side}"
        else:
            return f"{index_title} {index + 1}"


class TextService:
    @staticmethod
    def _has_header_in_first_segment(doc_check):
        chapter_data_check = doc_check.get("chapter", [])
        if isinstance(chapter_data_check, dict):
            chapter_data_check = list(chapter_data_check.values())
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
        """Returns rich source payloads with optional pagination, skipping empty pages."""
        db = MongoDatabase.get_db()
        range_info = ReferenceNavigator.parse_range_ref(ref)
        primary_ref = range_info["start"] if range_info else ref
        
        # Parse the primary ref to get index title
        parsed = ReferenceNavigator.parse_ref(primary_ref)
        index_title = parsed["index"]
        
        # Get the client to access both databases
        client = MongoDatabase.client
        talmudpedia_db = client["talmudpedia"]
        
        # Try to get the best version from the index in talmudpedia DB
        # Note: In production, consider caching the tree or loading it once
        index_doc = await talmudpedia_db.index.find_one({"title": index_title})
        preferred_version = None
        # We can't easily access bestHebrewVersion from index collection
        # Since it's only in the tree JSON. For now, we'll rely on the priority-based
        # selection in _find_best_document which should work well.
        # TODO: Consider loading tree JSON or adding bestHebrewVersion to index collection
        
        doc = await TextService._find_best_document(db, index_title, preferred_version)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Reference '{ref}' not found")
        
        # Fetch Hebrew title from index collection
        he_title = index_doc.get("heTitle") if index_doc else None
            
        chapter_data = doc.get("chapter", [])
        if isinstance(chapter_data, dict):
            chapter_data = list(chapter_data.values())
        is_talmud = "daf" in parsed
        
        # Determine current linear index
        current_index = -1
        if is_talmud:
            current_index = (parsed["daf_num"] - 1) * 2 + (0 if parsed["side"] == 'a' else 1)
        elif "chapter" in parsed:
            current_index = parsed["chapter"] - 1
            
        if current_index < 0:
             # Fallback or error? Let's assume 0 if something is weird but valid index
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
        indices_to_fetch.extend(reversed(before_indices))
        
        # Current Page (always include, even if empty, to show where user landed)
        # But if it's out of bounds, we handle it
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
            "he_title": he_title,
            "version_title": doc.get("versionTitle"),
            "language": doc.get("language")
        }

