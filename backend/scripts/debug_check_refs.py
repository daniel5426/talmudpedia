import json
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parents[1]
TREE_FILE = BASE_DIR / "sefaria_tree.json"
CHUNK_DIR = BASE_DIR / "library_chunks"

def check_refs(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    missing = []
    for node in nodes:
        if not node.get("ref"):
            missing.append({
                "title": node.get("title"),
                "type": node.get("type"),
                "slug": node.get("slug")
            })
        
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
            missing.extend(check_refs(children))
    return missing

if __name__ == "__main__":
    with open(TREE_FILE, "r") as f:
        tree = json.load(f)
    missing_refs = check_refs(tree)
    print(f"Total nodes missing 'ref': {len(missing_refs)}")
    if missing_refs:
        print("\nSome nodes missing 'ref':")
        for m in missing_refs[:20]:
            print(f"  {m}")
