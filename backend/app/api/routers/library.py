from fastapi import APIRouter, HTTPException, Response, Query
import json
from pathlib import Path
import os
import re
from typing import List, Dict, Any, Tuple
from collections import OrderedDict
from rapidfuzz import process, fuzz

router = APIRouter()

BASE_BACKEND = Path(__file__).resolve().parents[3]
TREE_FILE = BASE_BACKEND / "sefaria_tree.json"
CHUNK_DIR = BASE_BACKEND / "library_chunks"
ROOT_FILE = CHUNK_DIR / "root.json"
SEARCH_FILE = CHUNK_DIR / "search_index.json"
root_cache: List[Dict[str, Any]] | None = None
chunk_cache: Dict[str, Tuple[float, Any]] = {}
search_index_cache: List[Dict[str, Any]] | None = None
token_index_cache: Dict[str, List[int]] | None = None
search_index_mtime: float | None = None
result_cache: OrderedDict[str, List[Dict[str, Any]]] = OrderedDict()
RESULT_CACHE_SIZE = 128


def normalize_search_text(value: str) -> str:
    if not value:
        return ""
    lowered = str(value).lower()
    cleaned = re.sub(r"[׳״\"']", " ", lowered)
    cleaned = re.sub(r"[^0-9a-z\u0590-\u05ff\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()

def load_full_tree():
    if TREE_FILE.exists():
        with open(TREE_FILE, "r") as f:
            return json.load(f)
    alt = BASE_BACKEND / "backend" / "sefaria_tree.json"
    if alt.exists():
        with open(alt, "r") as f:
            return json.load(f)
    raise HTTPException(status_code=503, detail="Library menu is being built. Please try again later.")


def load_search_index():
    global search_index_cache, token_index_cache, search_index_mtime
    current_mtime = SEARCH_FILE.stat().st_mtime if SEARCH_FILE.exists() else None
    if (
        search_index_cache is not None
        and token_index_cache is not None
        and search_index_mtime is not None
        and current_mtime is not None
        and current_mtime == search_index_mtime
        and search_index_cache
        and "_he_ref_norm" in search_index_cache[0]
    ):
        return search_index_cache
    if not SEARCH_FILE.exists():
        raise HTTPException(status_code=503, detail="Search index not available")
    try:
        with open(SEARCH_FILE, "r") as f:
            raw = json.load(f)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid search index")
    # Accept both list and dict formats; if dict, wrap in list
    if isinstance(raw, dict):
        raw = [raw]
    cleaned: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, str):
                try:
                    entry = json.loads(entry)
                except Exception:
                    continue
            if not isinstance(entry, dict):
                continue
            title = entry.get("title") or ""
            he_title = entry.get("heTitle") or ""
            he_ref = entry.get("heRef") or ""
            path = entry.get("path") or []
            path_he = entry.get("path_he") or []
            parts = [title, he_title] + path + path_he
            ref = entry.get("ref") or ""
            parts.append(ref)
            if he_ref:
                parts.append(he_ref)
            blob = " ".join(str(p) for p in parts if p)
            normalized = normalize_search_text(blob)
            he_ref_norm = normalize_search_text(he_ref)
            he_title_norm = normalize_search_text(he_title)
            title_norm = normalize_search_text(title)
            ref_norm = normalize_search_text(ref)
            entry["_he_ref_norm"] = he_ref_norm
            entry["_he_title_norm"] = he_title_norm
            entry["_title_norm"] = title_norm
            entry["_ref_norm"] = ref_norm
            tokens = set()
            for field in (he_ref_norm, he_title_norm, title_norm, ref_norm, normalized):
                if field:
                    tokens.update(field.split())
            entry["_tokens"] = tokens
            entry["_search_blob"] = normalized
            cleaned.append(entry)
    search_index_cache = cleaned
    token_index: Dict[str, List[int]] = {}
    for idx, entry in enumerate(cleaned):
        for token in entry.get("_tokens", []):
            token_index.setdefault(token, []).append(idx)
    token_index_cache = token_index
    search_index_mtime = current_mtime
    return cleaned


@router.get("/menu", response_model=List[Dict[str, Any]])
async def get_library_menu(response: Response):
    global root_cache
    if root_cache is None:
        if os.path.exists(ROOT_FILE):
            try:
                with open(ROOT_FILE, "r") as f:
                    root_cache = json.load(f)
            except json.JSONDecodeError:
                raise HTTPException(status_code=500, detail="Invalid menu data")
        else:
            root_cache = load_full_tree()
    response.headers["Cache-Control"] = "public, max-age=86400, immutable"
    return root_cache


@router.get("/menu/{slug}", response_model=List[Dict[str, Any]])
async def get_library_chunk(slug: str, response: Response):
    chunk_path = os.path.join(CHUNK_DIR, f"{slug}.json")
    path_obj = Path(chunk_path)
    if not path_obj.exists():
        raise HTTPException(status_code=404, detail="Chunk not found")
    mtime = path_obj.stat().st_mtime
    cached = chunk_cache.get(slug)
    if cached and cached[0] == mtime:
        response.headers["Cache-Control"] = "public, max-age=86400, immutable"
        return cached[1]
    try:
        with open(path_obj, "r") as f:
            data = json.load(f)
            chunk_cache[slug] = (mtime, data)
            response.headers["Cache-Control"] = "public, max-age=86400, immutable"
            return data
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid menu data")


@router.get("/search", response_model=List[Dict[str, Any]])
async def search_library(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=50)):
    raw_index = load_search_index()
    if not raw_index:
        return []
    q_norm = normalize_search_text(q)
    if not q_norm or len(q_norm) < 2:
        return []
    cached = result_cache.get(q_norm)
    if cached is not None:
        result_cache.move_to_end(q_norm)
        return cached
    q_tokens = set(q_norm.split())

    token_index = token_index_cache or {}
    candidate_indices: List[int] = []
    if q_tokens:
        lists = [token_index.get(t) for t in q_tokens if t in token_index]
        lists = [lst for lst in lists if lst]
        if lists:
            lists.sort(key=len)
            intersect = set(lists[0])
            for lst in lists[1:]:
                intersect.intersection_update(lst)
                if not intersect:
                    break
            if intersect:
                candidate_indices = list(intersect)
        if not candidate_indices and lists:
            union_set = set()
            for lst in lists:
                union_set.update(lst)
            candidate_indices = list(union_set)
    if not candidate_indices:
        candidate_indices = list(range(len(raw_index)))
    if len(candidate_indices) > 800:
        candidate_indices = candidate_indices[:800]

    choices = []
    choice_to_idx = []
    for idx in candidate_indices:
        entry = raw_index[idx]
        he_ref = entry.get("_he_ref_norm") or ""
        he_title = entry.get("_he_title_norm") or ""
        ref = entry.get("_ref_norm") or ""
        title = entry.get("_title_norm") or ""
        choice = " ".join(p for p in (he_ref, he_title, ref, title) if p) or entry.get("_search_blob", "")
        choices.append(choice)
        choice_to_idx.append(idx)

    matches = process.extract(
        q_norm,
        choices,
        processor=None,
        scorer=fuzz.token_set_ratio,
        limit=max(limit * 3, 50),
        score_cutoff=60,
    )

    fallback_ranked = []
    for idx, entry in enumerate(raw_index):
        is_commentary_path = any("מפרשים" in str(p) for p in entry.get("path_he") or []) or any("commentary" in str(p).lower() for p in entry.get("path") or [])
        if is_commentary_path:
            continue
        he_ref_tokens = set((entry.get("_he_ref_norm") or "").split())
        if he_ref_tokens and he_ref_tokens.issubset(q_tokens) and len(he_ref_tokens) > 0 and len(he_ref_tokens) <= len(q_tokens) + 1:
            fallback_ranked.append((500, len(entry.get("path_he") or entry.get("path") or []), idx))

    ranked = []
    seen = set()
    for choice, score, match_idx in matches:
        entry_idx = choice_to_idx[match_idx]
        if entry_idx in seen:
            continue
        seen.add(entry_idx)
        raw_entry = raw_index[entry_idx]
        he_ref_norm = raw_entry.get("_he_ref_norm") or ""
        he_title_norm = raw_entry.get("_he_title_norm") or ""
        path_he = raw_entry.get("path_he") or []
        path_en = raw_entry.get("path") or []
        path_len = len(path_he or path_en)
        score_adj = score
        if he_ref_norm == q_norm:
            score_adj += 80
        elif he_ref_norm.startswith(q_norm):
            score_adj += 30
        elif q_norm in he_ref_norm:
            score_adj += 15
        else:
            he_ref_tokens = set(he_ref_norm.split()) if he_ref_norm else set()
            if he_ref_tokens:
                tokens_len = len(he_ref_tokens)
                overlap = len(he_ref_tokens & q_tokens)
                if overlap == len(he_ref_tokens) and overlap > 0:
                    score_adj += 70
                elif q_tokens and q_tokens.issubset(he_ref_tokens) and len(he_ref_tokens) <= len(q_tokens) + 1:
                    score_adj += 40
                elif overlap:
                    score_adj += 15
                if tokens_len <= len(q_tokens):
                    score_adj += 10
                elif tokens_len <= len(q_tokens) + 1:
                    score_adj += 50
                else:
                    score_adj -= (tokens_len - len(q_tokens) - 1) * 20
        if he_title_norm == q_norm:
            score_adj += 20
        is_commentary_path = any("מפרשים" in str(p) for p in path_he) or any("commentary" in str(p).lower() for p in path_en)
        if is_commentary_path:
            score_adj -= 40
        else:
            score_adj += 60
        if path_len > 0:
            if path_len <= 3:
                score_adj += 30
            else:
                excess = max(path_len - 3, 0)
                score_adj -= excess * 8
        ranked.append((score_adj, path_len, entry_idx))
    ranked.extend(fallback_ranked)

    ranked.sort(key=lambda x: (-x[0], x[1]))
    primary_candidates = []
    for _, _, entry_idx in ranked:
        entry = raw_index[entry_idx]
        is_commentary_path = any("מפרשים" in str(p) for p in entry.get("path_he") or []) or any("commentary" in str(p).lower() for p in entry.get("path") or [])
        if is_commentary_path:
            continue
        he_ref_tokens = set((entry.get("_he_ref_norm") or "").split())
        if not he_ref_tokens:
            continue
        overlap = len(he_ref_tokens & q_tokens)
        primary_candidates.append((overlap, len(he_ref_tokens), entry_idx))
    primary_candidates.sort(key=lambda x: (-x[0], x[1]))

    primary = []
    secondary = []
    for score_adj, _, entry_idx in ranked:
        entry = dict(raw_index[entry_idx])
        is_commentary_path = any("מפרשים" in str(p) for p in entry.get("path_he") or []) or any("commentary" in str(p).lower() for p in entry.get("path") or [])
        entry.pop("_search_blob", None)
        entry.pop("_tokens", None)
        entry.pop("_he_ref_norm", None)
        entry.pop("_he_title_norm", None)
        entry.pop("_title_norm", None)
        entry.pop("_ref_norm", None)
        entry["score"] = score_adj
        if is_commentary_path:
            secondary.append(entry)
        else:
            primary.append(entry)
    prioritized_ids = {idx for _, _, idx in primary_candidates[:3]}
    prioritized = [p for p in primary if p.get("ref") in {raw_index[idx].get("ref") for idx in prioritized_ids}]
    remaining_primary = [p for p in primary if p not in prioritized]
    results = (prioritized + remaining_primary + secondary)[:limit]

    if len(result_cache) >= RESULT_CACHE_SIZE:
        result_cache.popitem(last=False)
    result_cache[q_norm] = results
    return results
