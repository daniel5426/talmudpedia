import json
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parents[1]
TREE_FILE = BASE_DIR / "sefaria_tree.json"
CHUNK_DIR = BASE_DIR / "library_chunks"

def count_nodes(nodes: List[Dict[str, Any]]) -> int:
    count = 0
    for node in nodes:
        count += 1
        children = node.get("children") or []
        if not children and node.get("hasChildren") and node.get("slug"):
            slug = node["slug"]
            chunk_file = CHUNK_DIR / f"{slug}.json"
            if chunk_file.exists():
                with open(chunk_file, "r") as f:
                    children = json.load(f)
        
        if children:
            count += count_nodes(children)
    return count

if __name__ == "__main__":
    if TREE_FILE.exists():
        with open(TREE_FILE, "r") as f:
            tree = json.load(f)
        total = count_nodes(tree)
        print(f"Total nodes in JSON tree (including chunks): {total}")
    else:
        print("Tree file not found")
