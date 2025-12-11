from fastapi import APIRouter, HTTPException, Query, Path
from typing import Optional, Dict, Any
from app.db.connection import MongoDatabase
from app.db.models.sefaria import Text
from app.services.text.navigator import ReferenceNavigator, ComplexTextNavigator, RangeContext

router = APIRouter()

class TextService:
    @staticmethod
    def _first_ref_from_schema(index_title: str, schema: Dict[str, Any]) -> Optional[str]:
        """
        Build a best-effort first reference from the schema when no explicit location
        is provided. Walks the first child chain until a JaggedArrayNode is found.
        """
        path_parts = [index_title]

        def primary_en(node: Dict[str, Any]) -> Optional[str]:
            for t in node.get("titles", []):
                if t.get("lang") == "en" and t.get("primary"):
                    return t.get("text")
            return node.get("title") or node.get("key")

        current = schema
        while current:
            nodes = current.get("nodes", [])
            if not nodes:
                break
            current = nodes[0]
            if current.get("default"):
                continue
            title = primary_en(current)
            if title:
                path_parts.append(title)
            if current.get("nodeType") == "JaggedArrayNode":
                addr_types = current.get("addressTypes") or []
                if addr_types and isinstance(addr_types[0], str) and addr_types[0].lower() == "talmud":
                    return f"{', '.join(path_parts)} 1a" if len(path_parts) > 1 else f"{path_parts[0]} 1a"
                return f"{', '.join(path_parts)} 1" if len(path_parts) > 1 else f"{path_parts[0]} 1"

        return None
    @staticmethod
    def _normalize_chapter_data(chapter_data):
        if isinstance(chapter_data, dict):
            if 'default' in chapter_data:
                return chapter_data['default']
            return list(chapter_data.values())[0] if chapter_data else []
        return chapter_data if isinstance(chapter_data, list) else []
    
    @staticmethod
    def _build_he_ref(doc, page_parsed, index_title: str):
        base = doc.get("heTitle") or doc.get("heRef") or index_title
        if "daf" in page_parsed:
            he_num = ComplexTextNavigator.encode_hebrew_numeral(page_parsed["daf_num"])
            suffix = "." if page_parsed.get("side") == "a" else ":"
            return f"{base} {he_num}{suffix}"
        if "chapter" in page_parsed:
            he_num = ComplexTextNavigator.encode_hebrew_numeral(page_parsed["chapter"])
            return f"{base} {he_num}"
        return base
    
    @staticmethod
    def _daf_to_linear(daf_num: int, side: str) -> int:
        # Array index: 0->1a,1->1b,2->2a,...
        return (daf_num - 1) * 2 + (0 if side == 'a' else 1)

    @staticmethod
    def _flatten_segments(content):
        flat = []
        def rec(x):
            if isinstance(x, list):
                for y in x:
                    rec(y)
            else:
                if isinstance(x, str):
                    if x.strip():
                        flat.append(x)
                else:
                    flat.append(x)
        rec(content)
        return flat
    
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
    async def _find_best_document(db, index_title: str, preferred_version: Optional[str] = None, ref: Optional[str] = None, schema: Optional[Dict[str, Any]] = None):
        """Find best text document, optionally preferring a specific version and filtering by ref coverage."""
        if preferred_version:
            # Note: Logic for strict preferred version filtering
            pass

        all_he_docs = await db.texts.find({
            "title": {"$regex": f"^{index_title}$", "$options": "i"},
            "language": "he"
        }).to_list(length=None)
        
        if all_he_docs:
            if ref:
                relevant_docs = []
                tokens = ReferenceNavigator.tokenize_ref(ref)
                
                for d in all_he_docs:
                    sec_ref = d.get("sectionRef")
                    if not sec_ref:
                        relevant_docs.append(d)
                        continue
                        
                    sec_tokens = ReferenceNavigator.tokenize_ref(sec_ref)
                    if len(tokens) >= len(sec_tokens):
                        match = True
                        for i in range(len(sec_tokens)):
                            if tokens[i].lower() != sec_tokens[i].lower():
                                match = False
                                break
                        if match:
                            relevant_docs.append(d)
                
                if relevant_docs:
                    all_he_docs = relevant_docs
            
            if preferred_version:
                pref_docs = [d for d in all_he_docs if d.get("versionTitle") == preferred_version]
                if pref_docs:
                    return pref_docs[0]

            if schema and ref:
                 def priority_key(d):
                     p = d.get("priority")
                     try:
                         return float(p)
                     except:
                         return 0
                 
                 sorted_docs = sorted(all_he_docs, key=priority_key, reverse=True)
                 
                 for d in sorted_docs:
                     try:
                         res = ComplexTextNavigator.navigate_to_section(d, schema, ref, None)
                         c = res.get("content")
                         if c and not ComplexTextNavigator.is_content_empty(c):
                             return d
                     except:
                         continue

            versions_with_priority = [v for v in all_he_docs if "priority" in v and v["priority"] is not None]
            
            if versions_with_priority:
                best_doc = max(versions_with_priority, key=lambda v: float(v["priority"]) if isinstance(v["priority"], (int, float)) else 0)
                return best_doc
            
            for candidate_doc in all_he_docs:
                if TextService._has_header_in_first_segment(candidate_doc):
                    return candidate_doc
            if all_he_docs:
                return all_he_docs[0]
        
        doc = await db.texts.find_one({"title": index_title, "language": "he"})
        return doc

    @staticmethod
    def _handle_daf(parsed, chapter_data, page_result, range_ctx, is_main_page):
        daf_num = parsed["daf_num"]
        side = parsed["side"]
        line = parsed.get("line")
        daf_index = TextService._daf_to_linear(daf_num, side)
        if daf_index >= len(chapter_data) or daf_index < 0:
            return None
        daf_content = chapter_data[daf_index]
        segments = TextService._flatten_segments(daf_content)
        if not segments:
            return None
        page_result["segments"] = segments
        if is_main_page and line is not None and not range_ctx.raw:
            line_index = line - 1
            if 0 <= line_index < len(segments):
                page_result["highlight_index"] = line_index
                page_result["highlight_indices"] = [line_index]
        if range_ctx.raw:
            for i in range(len(segments)):
                if ReferenceNavigator.is_in_range(i, parsed, range_ctx):
                    page_result["highlight_indices"].append(i)
            if page_result["highlight_indices"]:
                page_result["highlight_index"] = page_result["highlight_indices"][0]
        return page_result
    
    @staticmethod
    def _handle_chapter(parsed, chapter_data, page_result, range_ctx, is_main_page):
        """Processes chapter-based pagination blocks."""
        chapter_num = parsed["chapter"] - 1
        if chapter_num >= len(chapter_data):
            return None
        chapter_content = chapter_data[chapter_num]
        segments = TextService._flatten_segments(chapter_content)
        if not segments:
            return None
        page_result["segments"] = segments
        if is_main_page and "verse" in parsed and parsed["verse"] is not None and not range_ctx.raw:
            verse_num = parsed["verse"] - 1
            if 0 <= verse_num < len(segments):
                page_result["highlight_index"] = verse_num
                page_result["highlight_indices"] = [verse_num]
        if range_ctx.raw:
            for i in range(len(segments)):
                if ReferenceNavigator.is_in_range(i, parsed, range_ctx):
                    page_result["highlight_indices"].append(i)
            if page_result["highlight_indices"]:
                page_result["highlight_index"] = page_result["highlight_indices"][0]
        return page_result

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

def _schema_has_talmud_default(schema: Dict[str, Any]) -> bool:
    if not schema:
        return False
    for child in schema.get("nodes", []):
        if child.get("default"):
            addr = child.get("addressTypes") or []
            if any(isinstance(t, str) and t.lower() == "talmud" for t in addr):
                return True
    return False


@router.get("/source/{ref:path}")
async def get_source_text(
    ref: str, 
    pages_before: int = Query(0, description="Number of pages/sections to fetch before the reference"), 
    pages_after: int = Query(0, description="Number of pages/sections to fetch after the reference")
):
    """Returns rich source payloads with optional pagination, supporting both simple and complex texts."""
    db = MongoDatabase.get_db()
    range_info = ReferenceNavigator.parse_range_ref(ref)
    primary_ref = range_info["start"] if range_info else ref
    
    parsed = ReferenceNavigator.parse_ref(primary_ref)
    index_title = parsed["index"]
    
    index_doc = await db.index.find_one({"title": index_title})
    schema = index_doc.get("schema", {}) if index_doc else {}
    
    if "chapter" in parsed and "daf" not in parsed and _schema_has_talmud_default(schema):
        primary_ref = f"{index_title} {parsed['chapter']}a"
        parsed = ReferenceNavigator.parse_ref(primary_ref)
    
    preferred_version = None

    # If the ref is just a bare book title, redirect to the first section/page
    if not any(k in parsed for k in ["chapter", "daf", "verse", "side", "line"]):
        first_ref = TextService._first_ref_from_schema(index_title, schema) if schema else None
        if first_ref:
            primary_ref = first_ref
            parsed = ReferenceNavigator.parse_ref(primary_ref)
    
    doc = await TextService._find_best_document(db, index_title, preferred_version, ref=primary_ref, schema=schema)
    
    if not doc and "," in primary_ref:
        base_title = primary_ref.split(",")[0].strip()
        if not index_doc:
            index_doc = await db.index.find_one({"title": base_title})
            schema = index_doc.get("schema", {}) if index_doc else {}
        
        doc = await TextService._find_best_document(db, base_title, preferred_version, ref=primary_ref, schema=schema)
        if doc:
            index_title = base_title
    
    if not doc:
        raise HTTPException(status_code=404, detail=f"Reference '{ref}' not found")

    nav_result = ComplexTextNavigator.navigate_to_section(doc, schema, primary_ref, index_doc)
    content = nav_result.get("content")
    he_ref = nav_result.get("heRef") or doc.get("heRef") or doc.get("heTitle")

    if content is None or ComplexTextNavigator.is_content_empty(content):
        raise HTTPException(status_code=404, detail=f"Content not found for reference '{ref}'")
    
    is_talmud = "daf" in parsed
    
    if nav_result.get("is_complex") and not nav_result.get("force_single_page"):
         
        full_content = nav_result.get("full_content")
        current_idx = nav_result.get("current_index")
        
        if full_content and current_idx is not None and isinstance(full_content, list):
            
            base_ref = primary_ref
            import re
            match = re.search(r"(\d+)$", primary_ref)
            if match:
                base_ref = primary_ref[:match.start()].strip().rstrip(',')
            
            total_len = len(full_content)
            indices_to_fetch = []
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
                prev_ref = ComplexTextNavigator.get_prev_section_ref(doc.get("title", ""), schema, primary_ref)
                if prev_ref:
                    can_load_top = True
                    if pages_before > count:
                        remaining_before = pages_before - count
                        prev_nav_result = ComplexTextNavigator.navigate_to_section(doc, schema, prev_ref, index_doc)
                        if prev_nav_result.get("content") and prev_nav_result.get("is_complex"):
                            prev_full = prev_nav_result.get("full_content") 
                            if not prev_full and isinstance(prev_nav_result.get("content"), list):
                                prev_full = prev_nav_result.get("content")
                            
                            prev_node = prev_nav_result.get("node", {})
                            if prev_node.get("depth") == 1:
                                prev_full_heref = prev_nav_result.get("base_he_ref") or prev_nav_result.get("heRef")
                                extra_pages_before.insert(0, {
                                    "ref": prev_ref,
                                    "he_ref": ComplexTextNavigator.strip_book_title_from_heref(prev_full_heref),
                                    "full_he_ref": prev_full_heref,
                                    "segments": prev_full, 
                                    "highlight_index": None,
                                    "highlight_indices": []
                                })
                            else:
                                prev_he_ref = prev_nav_result.get("base_he_ref") or prev_nav_result.get("heRef")
                                if prev_full:
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
                                            "full_he_ref": full_seg_he_ref,
                                            "segments": [seg_content] if isinstance(seg_content, str) else seg_content,
                                            "highlight_index": None,
                                            "highlight_indices": []
                                        })
                                        
            indices_to_fetch.append(current_idx)
            
            scan = current_idx + 1
            count = 0
            while scan < total_len and count < pages_after:
                if not ComplexTextNavigator.is_content_empty(full_content[scan]):
                    indices_to_fetch.append(scan)
                    count += 1
                scan += 1
            can_load_bottom = (scan < total_len)

            current_node = nav_result.get("node", {})
            current_node_depth = current_node.get("depth")
            addr_types = current_node.get("addressTypes") or []
            is_talmud_node = any(isinstance(t, str) and t.lower() == "talmud" for t in addr_types)

            pages = []
            main_page_index = 0
            
            base_he_ref = nav_result.get("base_he_ref") or nav_result.get("heRef")
            full_main_heref = base_he_ref

            if current_node_depth == 1:
                page_ref = nav_result.get("ref", primary_ref)

                page_res = {
                    "ref": page_ref,
                    "he_ref": ComplexTextNavigator.strip_book_title_from_heref(base_he_ref), 
                    "full_he_ref": base_he_ref,
                    "segments": full_content,
                    "highlight_index": current_idx if current_idx != 0 else None,
                    "highlight_indices": []
                }
                pages.append(page_res)
                can_load_bottom = False 
                count = 0

                added = False
                next_ref = ComplexTextNavigator.get_next_section_ref(doc.get("title", ""), schema, primary_ref)
                if next_ref:
                    can_load_bottom = True
                    if pages_after > count:
                        next_nav_result = ComplexTextNavigator.navigate_to_section(doc, schema, next_ref, index_doc)
                        if next_nav_result.get("content") and next_nav_result.get("is_complex") and not ComplexTextNavigator.is_content_empty(next_nav_result.get("content")):
                            next_full = next_nav_result.get("full_content") or (next_nav_result.get("content") if isinstance(next_nav_result.get("content"), list) else [next_nav_result.get("content")])
                            next_he_ref = next_nav_result.get("base_he_ref") or next_nav_result.get("heRef")
                            
                            next_node = next_nav_result.get("node", {})
                            next_depth = next_node.get("depth")

                            if next_depth == 1:
                                pages.append({
                                    "ref": next_ref,
                                    "he_ref": ComplexTextNavigator.strip_book_title_from_heref(next_he_ref),
                                    "full_he_ref": next_he_ref, 
                                    "segments": next_full,
                                    "highlight_index": None,
                                    "highlight_indices": []
                                })
                                
                                next_next_ref = ComplexTextNavigator.get_next_section_ref(doc.get("title", ""), schema, next_ref)
                                can_load_bottom = bool(next_next_ref)
                                added = True
                            else:
                                remaining_pages = pages_after - count
                                slice_end = min(len(next_full), remaining_pages) 
                                for k in range(slice_end):
                                    seg_content = next_full[k]
                                    seg_ref = f"{next_ref}:{k+1}"
                                    full_seg_he_ref = next_he_ref
                                    if full_seg_he_ref:
                                        full_seg_he_ref += f" {ComplexTextNavigator.encode_hebrew_numeral(k+1)}"
                                    seg_he_ref = ComplexTextNavigator.strip_book_title_from_heref(full_seg_he_ref)

                                    pages.append({
                                        "ref": seg_ref,
                                        "he_ref": seg_he_ref,
                                        "full_he_ref": full_seg_he_ref,
                                        "segments": [seg_content] if isinstance(seg_content, str) else seg_content,
                                        "highlight_index": None,
                                        "highlight_indices": []
                                    })
                                
                                can_load_bottom = len(next_full) > slice_end
                                if not can_load_bottom:
                                    next_next_ref = ComplexTextNavigator.get_next_section_ref(doc.get("title", ""), schema, next_ref)
                                    can_load_bottom = bool(next_next_ref)
                                added = True
                if not added and pages_after > count:
                    chapter_root = doc.get("chapter", {})
                    default_content = None
                    if isinstance(chapter_root, dict):
                        default_content = chapter_root.get("default")
                    elif isinstance(chapter_root, list):
                        default_content = chapter_root
                    if isinstance(default_content, list) and default_content:
                        first_idx = None
                        for i, v in enumerate(default_content):
                            if not ComplexTextNavigator.is_content_empty(v):
                                first_idx = i
                                break
                        if first_idx is not None:
                            page_ref = ReferenceNavigator.get_ref_from_index(doc.get("title", ""), first_idx, True)
                            seg_content = default_content[first_idx]
                            segments = TextService._flatten_segments(seg_content)
                            he_title = doc.get("heTitle") or base_he_ref or doc.get("title", "")
                            daf_num = (first_idx // 2) + 1
                            side = "a" if first_idx % 2 == 0 else "b"
                            he_daf = ComplexTextNavigator.encode_hebrew_numeral(daf_num)
                            suffix = "." if side == "a" else ":"
                            full_page_he_ref = f"{he_title} {he_daf}{suffix}".strip()
                            page_he_ref = ComplexTextNavigator.strip_book_title_from_heref(full_page_he_ref)
                            pages.append({
                                "ref": page_ref,
                                "he_ref": page_he_ref,
                                "full_he_ref": full_page_he_ref,
                                "segments": segments,
                                "highlight_index": None,
                                "highlight_indices": []
                            })
                            can_load_bottom = any(not ComplexTextNavigator.is_content_empty(x) for x in default_content[first_idx + 1:])

            else:
                for i, idx in enumerate(indices_to_fetch):
                    if idx == current_idx:
                        main_page_index = i
                    
                    if is_talmud_node:
                        page_ref = ReferenceNavigator.get_ref_from_index(doc.get("title", ""), idx, True)
                        daf_num = (idx // 2) + 1
                        side = "a" if idx % 2 == 0 else "b"
                        he_daf = ComplexTextNavigator.encode_hebrew_numeral(daf_num)
                        suffix = "." if side == "a" else ":"
                        full_page_he_ref = f"{doc.get('heTitle') or base_he_ref or doc.get('title', '')} {he_daf}{suffix}".strip()
                        page_he_ref = ComplexTextNavigator.strip_book_title_from_heref(full_page_he_ref)
                        if idx == current_idx:
                            full_main_heref = full_page_he_ref
                    else:
                        page_ref = f"{base_ref} {idx + 1}".strip()
                        
                        if base_he_ref:
                            he_num = ComplexTextNavigator.encode_hebrew_numeral(idx + 1)
                            full_page_he_ref = f"{base_he_ref} {he_num}"
                            page_he_ref = ComplexTextNavigator.strip_book_title_from_heref(full_page_he_ref)
                            if idx == current_idx:
                                full_main_heref = full_page_he_ref
                        else:
                            page_he_ref = nav_result.get("heRef")
                            full_page_he_ref = None
                    
                    seg_content = full_content[idx]
                    segments = seg_content if isinstance(seg_content, list) else [seg_content]
                    
                    page_res = {
                        "ref": page_ref,
                        "he_ref": page_he_ref,
                        "full_he_ref": full_page_he_ref if base_he_ref else None,
                        "segments": segments,
                        "highlight_index": None,
                        "highlight_indices": []
                    }
                    
                    if idx == current_idx:
                        if is_talmud_node and "line" in parsed and parsed["line"]:
                            line_idx = parsed["line"] - 1
                            if 0 <= line_idx < len(segments):
                                page_res["highlight_index"] = line_idx
                                page_res["highlight_indices"] = [line_idx]
                        elif "verse" in parsed and parsed["verse"]:
                            v_idx = parsed["verse"] - 1
                            if 0 <= v_idx < len(segments):
                                page_res["highlight_index"] = v_idx
                                page_res["highlight_indices"] = [v_idx]
                    
                    pages.append(page_res)

            if not can_load_bottom:
                next_ref = ComplexTextNavigator.get_next_section_ref(doc.get("title", ""), schema, primary_ref)
                if next_ref:
                    can_load_bottom = True
                    
                    if pages_after > count:
                        next_nav_result = ComplexTextNavigator.navigate_to_section(doc, schema, next_ref, index_doc)
                        if next_nav_result.get("content") and next_nav_result.get("is_complex"):
                            next_full = next_nav_result.get("full_content") 
                            next_he_ref = next_nav_result.get("base_he_ref") or next_nav_result.get("heRef")
                            
                            if isinstance(next_full, list) and next_full:
                                remaining_pages = pages_after - count
                                slice_end = min(len(next_full), remaining_pages) 
                                
                                next_node = next_nav_result.get("node", {})
                                next_depth = next_node.get("depth")

                                if next_depth == 1:
                                    pages.append({
                                        "ref": next_ref,
                                        "he_ref": ComplexTextNavigator.strip_book_title_from_heref(next_he_ref),
                                        "full_he_ref": next_he_ref, 
                                        "segments": next_full,
                                        "highlight_index": None,
                                        "highlight_indices": []
                                    })
                                    
                                    next_next_ref = ComplexTextNavigator.get_next_section_ref(doc.get("title", ""), schema, next_ref)
                                    can_load_bottom = bool(next_next_ref)
                                else:
                                    for k in range(slice_end):
                                        seg_content = next_full[k]
                                        seg_ref = f"{next_ref}:{k+1}"
                                        full_seg_he_ref = next_he_ref
                                        if full_seg_he_ref:
                                            full_seg_he_ref += f" {ComplexTextNavigator.encode_hebrew_numeral(k+1)}"
                                        seg_he_ref = ComplexTextNavigator.strip_book_title_from_heref(full_seg_he_ref)

                                        pages.append({
                                            "ref": seg_ref,
                                            "he_ref": seg_he_ref,
                                            "full_he_ref": full_seg_he_ref,
                                            "segments": [seg_content] if isinstance(seg_content, str) else seg_content,
                                            "highlight_index": None,
                                            "highlight_indices": []
                                        })
                                    
                                    can_load_bottom = len(next_full) > slice_end
                                    if not can_load_bottom:
                                        next_next_ref = ComplexTextNavigator.get_next_section_ref(doc.get("title", ""), schema, next_ref)
                                        can_load_bottom = bool(next_next_ref)
            
            if extra_pages_before:
                pages = extra_pages_before + pages
                main_page_index += len(extra_pages_before)
            
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

        segments = content if isinstance(content, list) else [content]
        
        page_result = {
            "ref": primary_ref,
            "he_ref": he_ref,
            "segments": segments,
            "highlight_index": None,
            "highlight_indices": []
        }
        
        if "verse" in parsed and parsed["verse"]:
            v_idx = parsed["verse"] - 1
            if 0 <= v_idx < len(segments):
                page_result["highlight_index"] = v_idx
                page_result["highlight_indices"] = [v_idx]

        can_load_bottom = False
        extra_pages = []
        
        next_ref = ComplexTextNavigator.get_next_section_ref(doc.get("title", ""), schema, primary_ref)
        if next_ref:
             can_load_bottom = True
             if pages_after > 0:
                 next_nav_result = ComplexTextNavigator.navigate_to_section(doc, schema, next_ref, index_doc)
                 
                 if next_nav_result.get("content") and next_nav_result.get("is_complex"):
                     next_content = next_nav_result.get("content")
                     next_full = next_nav_result.get("full_content") or (next_content if isinstance(next_content, list) else [next_content])
                     next_he_ref = next_nav_result.get("heRef")
                     
                     next_node = next_nav_result.get("node", {})
                     next_depth = next_node.get("depth")

                     if next_depth == 1:
                         extra_pages.append({
                            "ref": next_ref,
                            "he_ref": ComplexTextNavigator.strip_book_title_from_heref(next_he_ref),
                            "full_he_ref": next_he_ref, 
                            "segments": next_full,
                            "highlight_index": None,
                            "highlight_indices": []
                        })
                        
                         next_next_ref = ComplexTextNavigator.get_next_section_ref(doc.get("title", ""), schema, next_ref)
                         can_load_bottom = bool(next_next_ref)
                             
                     else:
                         remaining_pages = pages_after
                         slice_end = min(len(next_full), remaining_pages)
                         
                         for k in range(slice_end):
                             seg_content = next_full[k]
                             seg_ref = f"{next_ref}:{k+1}"
                             
                             full_seg_he_ref = next_he_ref
                             if full_seg_he_ref:
                                 he_num = ComplexTextNavigator.encode_hebrew_numeral(k+1)
                                 full_seg_he_ref += f" {he_num}"
                             seg_he_ref = ComplexTextNavigator.strip_book_title_from_heref(full_seg_he_ref)
                                 
                             extra_pages.append({
                                "ref": seg_ref,
                                "he_ref": seg_he_ref,
                                "full_he_ref": full_seg_he_ref,
                                "segments": [seg_content] if isinstance(seg_content, str) else seg_content,
                                "highlight_index": None,
                                "highlight_indices": []
                            })
                         
                         can_load_bottom = len(next_full) > slice_end
                         if not can_load_bottom:
                             next_next_ref = ComplexTextNavigator.get_next_section_ref(doc.get("title", ""), schema, next_ref)
                             can_load_bottom = bool(next_next_ref)

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
    if nav_result.get("is_complex"):
         pass 

    chapter_data = doc.get("chapter", [])
    chapter_data = TextService._normalize_chapter_data(chapter_data)
    
    current_index = -1
    if is_talmud:
        current_index = TextService._daf_to_linear(parsed["daf_num"], parsed["side"])
    elif "chapter" in parsed:
        current_index = parsed["chapter"] - 1
    
    if current_index < 0:
        current_index = 0
    
    def has_content(idx):
        if 0 <= idx < len(chapter_data):
            content = chapter_data[idx]
            segs = TextService._flatten_segments(content)
            return len(segs) > 0
        return False
    
    indices_to_fetch = []
    
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
    
    if 0 <= current_index < len(chapter_data):
        indices_to_fetch.append(current_index)
    
    scan = current_index + 1
    count = 0
    while scan < len(chapter_data) and count < pages_after:
        if has_content(scan):
            indices_to_fetch.append(scan)
            count += 1
        scan += 1
        
    can_load_bottom = (scan < len(chapter_data))
    
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
        
        he_ref_value = TextService._build_he_ref(doc, page_parsed, index_title)
        page_result = {
            "ref": page_ref,
            "he_ref": he_ref_value,
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
        "he_ref": TextService._build_he_ref(doc, parsed, index_title),
        "version_title": doc.get("versionTitle"),
        "language": doc.get("language"),
        "can_load_more": {"top": can_load_top, "bottom": can_load_bottom}
    }
