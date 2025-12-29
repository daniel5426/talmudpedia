import json
from pathlib import Path
from collections import Counter
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parents[1]
TREE_FILE = BASE_DIR / "sefaria_tree.json"
CHUNK_DIR = BASE_DIR / "library_chunks"

def get_all_ids(nodes: List[Dict[str, Any]]) -> List[str]:
    ids = []
    for node in nodes:
        doc_id = node.get("ref") or node.get("slug") or node.get("title")
        if doc_id:
            ids.append(doc_id)
        
        children = node.get("children") or []
        if not children and node.get("hasChildren") and node.get("slug"):
            slug = node["slug"]
            chunk_file = CHUNK_DIR / f"{slug}.json"
            if chunk_file.exists():
                with open(chunk_file, "r") as f:
                    try:
                        children = json.load(f)
                    except:
                        pass
        
        if children:
            ids.extend(get_all_ids(children))
    return ids

if __name__ == "__main__":
    with open(TREE_FILE, "r") as f:
        tree = json.load(f)
    ids = get_all_ids(tree)
    counter = Counter(ids)
    duplicates = {k: v for k, v in counter.items() if v > 1}
    print(f"Total nodes: {len(ids)}")
    print(f"Unique IDs: {len(counter)}")
    print(f"Number of duplicate IDs: {len(duplicates)}")
    if duplicates:
        print("\nSome duplicates:")
        for k in list(duplicates.keys())[:10]:
            print(f"  {k}: {duplicates[k]} times")
