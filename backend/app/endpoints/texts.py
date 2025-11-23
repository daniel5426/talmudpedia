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


class TextService:
    @staticmethod
    async def fetch_page_data(db, page_ref: str, range_ctx: RangeContext, is_main_page: bool = False) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """Loads page content along with highlight metadata."""
        parsed = ReferenceNavigator.parse_ref(page_ref)
        index_title = parsed["index"]
        doc = await db.texts.find_one({"title": index_title})
        if not doc:
            doc = await db.texts.find_one({"title": {"$regex": f"^{index_title}$", "$options": "i"}})
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
        daf_index = (daf_num - 2) * 2 + (0 if side == 'a' else 1)
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
        """Returns rich source payloads with optional pagination."""
        db = MongoDatabase.get_db()
        range_info = ReferenceNavigator.parse_range_ref(ref)
        primary_ref = range_info["start"] if range_info else ref
        range_ctx = RangeContext(
            raw=range_info,
            start=ReferenceNavigator.parse_ref(range_info["start"]) if range_info else None,
            end=ReferenceNavigator.parse_ref(range_info["end"]) if range_info else None
        )
        main_page_data = await TextService.fetch_page_data(db, primary_ref, range_ctx, is_main_page=True)
        if main_page_data is None:
            raise HTTPException(status_code=404, detail=f"Reference '{ref}' not found")
        main_page, doc = main_page_data
        if pages_before == 0 and pages_after == 0:
            return {
                "ref": ref,
                "index_title": doc.get("title"),
                "version_title": doc.get("versionTitle"),
                "language": doc.get("language"),
                "segments": main_page["segments"],
                "highlight_index": main_page["highlight_index"],
                "highlight_indices": main_page["highlight_indices"]
            }
        pages: List[Dict[str, Any]] = []
        for i in range(pages_before, 0, -1):
            prev_ref = ReferenceNavigator.get_adjacent_refs(primary_ref, -i)
            if prev_ref:
                prev_data = await TextService.fetch_page_data(db, prev_ref, RangeContext(None, None, None))
                if prev_data:
                    prev_page, _ = prev_data
                    pages.append(prev_page)
        main_page_index = len(pages)
        pages.append(main_page)
        for i in range(1, pages_after + 1):
            next_ref = ReferenceNavigator.get_adjacent_refs(primary_ref, i)
            if next_ref:
                next_data = await TextService.fetch_page_data(db, next_ref, RangeContext(None, None, None))
                if next_data:
                    next_page, _ = next_data
                    pages.append(next_page)
        return {
            "pages": pages,
            "main_page_index": main_page_index,
            "index_title": doc.get("title"),
            "version_title": doc.get("versionTitle"),
            "language": doc.get("language")
        }

