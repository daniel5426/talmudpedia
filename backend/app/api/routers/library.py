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


def load_chunk(slug: str) -> List[Dict[str, Any]]:
    chunk_path = os.path.join(CHUNK_DIR, f"{slug}.json")
    path_obj = Path(chunk_path)
    if not path_obj.exists():
        raise HTTPException(status_code=404, detail="Chunk not found")
    mtime = path_obj.stat().st_mtime
    cached = chunk_cache.get(slug)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with open(path_obj, "r") as f:
            data = json.load(f)
            chunk_cache[slug] = (mtime, data)
            return data
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid menu data")


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
async def search_library(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=50), page: int = Query(1, ge=1)):
    raw_index = load_search_index()
    if not raw_index:
        return []
    q_norm = normalize_search_text(q)
    if not q_norm or len(q_norm) < 2:
        return []
    skip = (page - 1) * limit
    q_tokens = set(q_norm.split())
    section_token = _extract_section_token(q_norm)
    try:
        collection = MongoDatabase.get_collection("library_search")
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
            if cleaned_results:
                return cleaned_results
    except Exception:
        pass
    cached = result_cache.get(q_norm)
    if cached is not None:
        result_cache.move_to_end(q_norm)
        return cached

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


def select_best_entry(ref: str, entries: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    target = normalize_search_text(ref)
    if not target:
        return None
    best = None
    best_score = -1
    for entry in entries:
        he_ref_norm = entry.get("_he_ref_norm") or ""
        ref_norm = entry.get("_ref_norm") or ""
        title_norm = entry.get("_title_norm") or ""
        score = -1
        if target == he_ref_norm or target == ref_norm:
            score = 1000
        else:
            score = max(
                fuzz.token_set_ratio(target, he_ref_norm or ref_norm),
                fuzz.token_set_ratio(target, title_norm),
            )
        if score > best_score:
            best_score = score
            best = entry
    return best if best_score >= 50 else None


def ensure_root_loaded() -> List[Dict[str, Any]]:
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
    return root_cache or []


def find_node_by_path(path: List[str], path_he: List[str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any] | None, List[str], List[str]]:
    tree = ensure_root_loaded()
    current_level = tree
    parent = None
    parent_path = []
    parent_path_he = []
    for idx, title in enumerate(path):
        he_title = path_he[idx] if idx < len(path_he) else None
        node = next(
            (
                n
                for n in current_level
                if n.get("title") == title or (he_title and n.get("heTitle") == he_title)
            ),
            None,
        )
        if not node:
            return current_level, None, parent_path, parent_path_he
        if node.get("hasChildren") and not node.get("children") and node.get("slug"):
            node["children"] = load_chunk(node["slug"])
        if idx < len(path) - 1:
            parent = node
            parent_path = path[: idx + 1]
            parent_path_he = path_he[: idx + 1]
            current_level = node.get("children") or []
        else:
            parent_path = path[:-1]
            parent_path_he = path_he[:-1]
            return parent.get("children") if parent else tree, node, parent_path, parent_path_he
    return current_level, None, parent_path, parent_path_he


def slim_node(node: Dict[str, Any]) -> Dict[str, Any]:
    keys = ["title", "heTitle", "ref", "slug", "type"]
    return {k: node.get(k) for k in keys if k in node}


def load_children(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    if node.get("hasChildren") and not node.get("children") and node.get("slug"):
        node["children"] = load_chunk(node["slug"])
    return node.get("children") or []


def find_by_ref(
    nodes: List[Dict[str, Any]],
    ref: str,
    path: List[str],
    path_he: List[str],
    parent: Dict[str, Any] | None,
) -> Tuple[List[Dict[str, Any]] | None, Dict[str, Any] | None, List[str], List[str]]:
    for node in nodes:
        node_ref = node.get("ref")
        children = load_children(node)
        current_path = path + [node.get("title") or ""]
        current_path_he = path_he + [node.get("heTitle") or ""]
        if node_ref and node_ref == ref:
            siblings_level = nodes
            parent_path = path
            parent_path_he = path_he
            return siblings_level, node, parent_path, parent_path_he
        if children:
            found = find_by_ref(children, ref, current_path, current_path_he, node)
            if found[1] is not None:
                return found
    return None, None, [], []


@router.get("/siblings/{ref:path}", response_model=Dict[str, Any])
async def get_siblings(ref: str):
    mongo_doc = None
    try:
        collection = MongoDatabase.get_collection("library_siblings")
        mongo_doc = await collection.find_one({"ref": ref}, {"_id": 0})
    except Exception:
        mongo_doc = None

    entries = None
    entry = None
    resolved_ref = ref
    path: List[str] = []
    path_he: List[str] = []

    if mongo_doc is None:
        entries = load_search_index()
        if not entries:
            raise HTTPException(status_code=404, detail="Search index not available")
        entry = select_best_entry(ref, entries)
        if not entry:
            raise HTTPException(status_code=404, detail="Source not found")
        resolved_ref = entry.get("ref") or ref
        path = entry.get("path") or []
        path_he = entry.get("path_he") or []
        try:
            collection = MongoDatabase.get_collection("library_siblings")
            mongo_doc = await collection.find_one({"ref": resolved_ref}, {"_id": 0})
        except Exception:
            mongo_doc = None

    if mongo_doc:
        return mongo_doc

    root = ensure_root_loaded()
    siblings_level, current_node, parent_path, parent_path_he = find_by_ref(
        root, resolved_ref, [], [], None
    )
    if current_node is None:
        siblings_level, current_node, parent_path, parent_path_he = find_node_by_path(path, path_he)
    if current_node is None:
        raise HTTPException(status_code=404, detail="Source path not found in library")
    if siblings_level is None:
        siblings_level = []
    siblings = [slim_node(node) for node in siblings_level]
    parent_node = None
    if parent_path:
        parent_level, parent_node_candidate, _, _ = find_node_by_path(parent_path, parent_path_he)
        parent_node = slim_node(parent_node_candidate) if parent_node_candidate else None
        if parent_node_candidate and parent_node_candidate.get("hasChildren") and not parent_node_candidate.get("children") and parent_node_candidate.get("slug"):
            parent_node_candidate["children"] = load_chunk(parent_node_candidate["slug"])
            siblings = [slim_node(n) for n in parent_node_candidate.get("children") or siblings_level]
    return {
        "current_ref": resolved_ref,
        "path": path,
        "path_he": path_he,
        "parent_path": parent_path,
        "parent_path_he": parent_path_he,
        "parent": parent_node,
        "siblings": siblings,
    }
