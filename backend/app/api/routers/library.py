from fastapi import APIRouter, HTTPException, Response, Query
import json
from pathlib import Path
import os
import re
from typing import List, Dict, Any, Tuple
from collections import OrderedDict
from rapidfuzz import process, fuzz
from app.db.connection import MongoDatabase
from pymongo import DESCENDING

router = APIRouter()

# Configurable Cache for menu chunks
ENABLE_FULL_CACHE = os.getenv("ENABLE_FULL_LIBRARY_CACHE", "false").lower() == "true"
MENU_CACHE_SIZE = 20000 if ENABLE_FULL_CACHE else 128
menu_cache: Dict[str, List[Dict[str, Any]]] = {}
root_cache: List[Dict[str, Any]] | None = None

async def preload_library_cache():
    """Background task to load all categories into memory for instant menu speed.
    Only runs if ENABLE_FULL_LIBRARY_CACHE is true.
    """
    global root_cache
    if not ENABLE_FULL_CACHE:
        return
        
    try:
        print("Pre-loading library menu cache (High-RAM Mode)...")
        collection = MongoDatabase.get_sefaria_collection("library_siblings")
        
        # 1. Load root
        cursor = collection.find({"path": []}, {"_id": 0}).sort("title", 1)
        root_cache = await cursor.to_list(length=100)
        
        # 2. Load all navigation nodes (folders/categories)
        cursor = collection.find({"hasChildren": True}, {"_id": 1, "slug": 1, "ref": 1, "children": 1})
        count = 0
        async for doc in cursor:
            children = doc.get("children", [])
            if children:
                if "_id" in doc: menu_cache[doc["_id"]] = children
                if doc.get("slug"): menu_cache[doc["slug"]] = children
                if doc.get("ref"): menu_cache[doc["ref"]] = children
                count += 1
        print(f"Library menu cache warmed up: {count} folders loaded into RAM.")
    except Exception as e:
        print(f"Failed to preload library cache: {e}")
RESULT_CACHE_SIZE = 128


def normalize_search_text(value: str) -> str:
    if not value:
        return ""
    lowered = str(value).lower()
    cleaned = re.sub(r"[׳״\"']", "", lowered)
    cleaned = re.sub(r"[^0-9a-z\u0590-\u05ff\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _is_commentary_entry(entry: Dict[str, Any]) -> bool:
    path_he = entry.get("path_he") or []
    path_en = entry.get("path") or []
    return any("מפרשים" in str(p) for p in path_he) or any("commentary" in str(p).lower() for p in path_en)


def _extract_section_token(q_norm: str) -> str | None:
    parts = q_norm.split()
    if len(parts) < 2:
        return None
    last = parts[-1]
    prev = parts[-2] if len(parts) >= 2 else ""
    if last.isdigit():
        return last
    if not re.fullmatch(r"[\u0590-\u05ff]+", last):
        return None
    if prev in {"סימן", "סי", "סי׳", "ס׳", "פרק", "דף"} and 1 <= len(last) <= 6:
        return last
    if 1 <= len(last) <= 3:
        return last
    return None


def _with_spaced_hebrew_last_token(q: str) -> str | None:
    parts = normalize_search_text(q).split()
    if not parts:
        return None
    last = parts[-1]
    if re.fullmatch(r"[\u0590-\u05ff]{2,}", last):
        parts[-1] = " ".join(list(last))
        return " ".join(parts)
    return None


def _with_gershayim_hebrew_last_token(q: str) -> str | None:
    parts = normalize_search_text(q).split()
    if not parts:
        return None
    last = parts[-1]
    if not re.fullmatch(r"[\u0590-\u05ff]+", last):
        return None
    if len(last) == 1:
        parts[-1] = f"{last}׳"
        return " ".join(parts)
    if len(last) >= 2:
        parts[-1] = f"{last[:-1]}״{last[-1]}"
        return " ".join(parts)
    return None


def _mongo_search_strings(q: str) -> List[str]:
    base = re.sub(r"[׳״\"']", " ", str(q))
    base = re.sub(r"\s+", " ", base).strip()
    out = []
    for s in (base, normalize_search_text(q)):
        s = str(s or "").strip()
        if s and s not in out:
            out.append(s)
        spaced = _with_spaced_hebrew_last_token(s)
        if spaced and spaced not in out:
            out.append(spaced)
        gershayim = _with_gershayim_hebrew_last_token(s)
        if gershayim and gershayim not in out:
            out.append(gershayim)
    return out


def _entry_rank(entry: Dict[str, Any], q_norm: str, q_tokens: set[str], section_token: str | None) -> int:
    he_ref_norm = normalize_search_text(entry.get("heRef") or "")
    ref_norm = normalize_search_text(entry.get("ref") or "")
    he_title_norm = normalize_search_text(entry.get("heTitle") or "")
    title_norm = normalize_search_text(entry.get("title") or "")

    primary = he_ref_norm or ref_norm or he_title_norm or title_norm
    score = fuzz.token_set_ratio(q_norm, primary) if primary else 0

    if he_ref_norm == q_norm or ref_norm == q_norm:
        score += 250
    elif he_ref_norm.startswith(q_norm) or ref_norm.startswith(q_norm):
        score += 80
    elif q_norm and (q_norm in he_ref_norm or q_norm in ref_norm):
        score += 40

    he_ref_tokens = set(he_ref_norm.split()) if he_ref_norm else set()
    ref_tokens = set(ref_norm.split()) if ref_norm else set()
    combined_tokens = he_ref_tokens | ref_tokens
    if q_tokens and combined_tokens:
        overlap = len(q_tokens & combined_tokens)
        score += overlap * 18
        if q_tokens.issubset(combined_tokens):
            score += 110
        if combined_tokens.issubset(q_tokens):
            score += 60

    if section_token:
        he_title_tokens = set(he_title_norm.split()) if he_title_norm else set()
        title_tokens = set(title_norm.split()) if title_norm else set()
        all_tokens = combined_tokens | he_title_tokens | title_tokens
        if section_token in all_tokens:
            score += 220
        else:
            score -= 220

        entry_ref_for_section = he_ref_norm or ref_norm
        entry_last = None
        if entry_ref_for_section:
            for t in reversed(entry_ref_for_section.split()):
                if t.isdigit() or re.fullmatch(r"[\u0590-\u05ff]+", t):
                    entry_last = t
                    break
        if entry_last == section_token:
            score += 700
        else:
            score -= 700

    if _is_commentary_entry(entry):
        score -= 140
    else:
        score += 140

    path_len = len(entry.get("path_he") or entry.get("path") or [])
    if path_len <= 3:
        score += 25
    else:
        score -= (path_len - 3) * 6
    if entry.get("type") == "book" and section_token:
        score -= 120
    return int(score)

# Removed JSON-based loading functions (load_full_tree, load_search_index, load_chunk)


@router.get("/menu", response_model=List[Dict[str, Any]])
async def get_library_menu(response: Response):
    global root_cache
    if root_cache is not None:
        response.headers["Cache-Control"] = "public, max-age=86400, immutable"
        return root_cache
        
    try:
        collection = MongoDatabase.get_sefaria_collection("library_siblings")
        # Top-level nodes are those with an empty path
        cursor = collection.find({"path": []}, {"_id": 0}).sort("title", 1)
        root_cache = await cursor.to_list(length=100)
        
        response.headers["Cache-Control"] = "public, max-age=86400, immutable"
        return root_cache
    except Exception as e:
        print(f"Error fetching library menu from MongoDB: {e}")
        raise HTTPException(status_code=500, detail="Failed to load library menu")


@router.get("/menu/{identifier:path}", response_model=List[Dict[str, Any]])
async def get_library_chunk(identifier: str, response: Response):
    # Check cache first
    if identifier in menu_cache:
        response.headers["Cache-Control"] = "public, max-age=86400, immutable"
        return menu_cache[identifier]
        
    try:
        collection = MongoDatabase.get_sefaria_collection("library_siblings")
        
        # Prioritize _id lookup as it's the fastest indexed field
        doc = await collection.find_one({"_id": identifier}, {"children": 1})
        
        if not doc:
            # Fallback to slug or ref if not found by unique ID
            doc = await collection.find_one(
                {
                    "$or": [
                        {"slug": identifier},
                        {"ref": identifier}
                    ]
                },
                {"children": 1}
            )
        
        if doc and "children" in doc:
            children = doc["children"]
            # Manage cache size
            if len(menu_cache) >= MENU_CACHE_SIZE:
                menu_cache.pop(next(iter(menu_cache)))
            menu_cache[identifier] = children
            
            response.headers["Cache-Control"] = "public, max-age=86400, immutable"
            return children
        
        raise HTTPException(status_code=404, detail="Chunk not found")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching library chunk {identifier} from MongoDB: {e}")
        raise HTTPException(status_code=500, detail="Failed to load library chunk")


@router.get("/search", response_model=List[Dict[str, Any]])
async def search_library(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=50), page: int = Query(1, ge=1)):
    q_norm = normalize_search_text(q)
    if not q_norm or len(q_norm) < 2:
        return []
    skip = (page - 1) * limit
    q_tokens = set(q_norm.split())
    section_token = _extract_section_token(q_norm)
    
    try:
        collection = MongoDatabase.get_sefaria_collection("library_search")
        fetch_n = min(max(page * limit * 5, limit * 5), 1000)
        merged: Dict[str, Dict[str, Any]] = {}
        for search_str in _mongo_search_strings(q):
            mongo_cursor = collection.find(
                {"_id": {"$ne": "__meta__"}, "$text": {"$search": search_str}},
                {"score": {"$meta": "textScore"}},
            ).sort([("score", {"$meta": "textScore"})]).limit(fetch_n)
            batch = await mongo_cursor.to_list(length=fetch_n)
            for entry in batch:
                key = entry.get("ref") or entry.get("heRef") or entry.get("slug") or str(entry.get("_id") or "")
                if not key:
                    continue
                if key not in merged:
                    merged[key] = entry

        if not merged:
            regex = {"$regex": re.escape(q.strip()), "$options": "i"}
            mongo_cursor = collection.find(
                {
                    "_id": {"$ne": "__meta__"},
                    "$or": [
                        {"title": regex},
                        {"heTitle": regex},
                        {"ref": regex},
                        {"heRef": regex},
                        {"path_str": regex},
                        {"path_he_str": regex},
                    ],
                }
            ).limit(fetch_n)
            batch = await mongo_cursor.to_list(length=fetch_n)
            for entry in batch:
                key = entry.get("ref") or entry.get("heRef") or entry.get("slug") or str(entry.get("_id") or "")
                if not key:
                    continue
                if key not in merged:
                    merged[key] = entry

        if merged:
            ranked = sorted(
                merged.values(),
                key=lambda e: _entry_rank(e, q_norm, q_tokens, section_token),
                reverse=True,
            )
            page_slice = ranked[skip : skip + limit]
            cleaned_results = []
            for entry in page_slice:
                entry.pop("_id", None)
                cleaned_results.append(entry)
            return cleaned_results
            
    except Exception as e:
        print(f"Search error: {e}")
        pass

    return []


# Removed JSON-based traversal functions


@router.get("/siblings/{ref:path}", response_model=Dict[str, Any])
async def get_siblings(ref: str):
    try:
        # Immediately clean ref of any segment part (usually starting with a colon, e.g., "Book 58:1" -> "Book 58")
        # This handles the case where a search result ref includes a segment which isn't in library_siblings
        clean_ref = re.sub(r'[:]\d+(?:-\d+)?$', '', ref.strip())
        
        collection = MongoDatabase.get_sefaria_collection("library_siblings")
        # Try finding by exact cleaned ref first
        doc = await collection.find_one({"ref": clean_ref}, {"_id": 0})
        
        if not doc and clean_ref != ref:
            # If cleaned ref fails, try original ref (just in case the "segment" was actually needed)
            doc = await collection.find_one({"ref": ref}, {"_id": 0})

        if not doc:
            # If still not found, try by _id (slug or title)
            doc = await collection.find_one({"_id": clean_ref}, {"_id": 0})
            if not doc and clean_ref != ref:
                doc = await collection.find_one({"_id": ref}, {"_id": 0})
        
        if not doc:
            raise HTTPException(status_code=404, detail="Source not found in library")
            
        # Map fields to match fontend's LibrarySiblingsResponse
        path = doc.get("path") or []
        path_he = doc.get("path_he") or []
        
        return {
            "current_ref": doc.get("ref") or str(doc.get("_id") or ""),
            "path": path,
            "path_he": path_he,
            "parent_path": path[:-1] if path else [],
            "parent_path_he": path_he[:-1] if path_he else [],
            "parent": doc.get("parent"),
            "siblings": doc.get("siblings", []),
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching siblings for {ref}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
