import requests
import json
import os

BASE = "http://localhost:8000/api/source"

def fetch(ref, before=0, after=2):
    url = f"{BASE}/{ref}"
    params = {"pages_before": before, "pages_after": after}
    r = requests.get(url, params=params)
    if r.status_code != 200:
        print(f"  Status: {r.status_code}")
        try:
            print(f"  Response: {r.json()}")
        except:
            print(f"  Response: {r.text[:200]}")
        r.raise_for_status()
    return r.json()

def summarize(page):
    seg = page["segments"]
    first = ""
    if seg:
        s = seg[0] if isinstance(seg[0], str) else str(seg[0])
        first = s[:80].replace("\n", " ")
    return f'ref={page["ref"]} | he_ref={page.get("he_ref")} | segs={len(seg)} | first="{first}"'

def check_talmud_refs():
    print("\n=== Checking talmud.json for Rashbam on Bava Batra refs ===")
    talmud_path = "backend/library_chunks/talmud.json"
    if not os.path.exists(talmud_path):
        print(f"  File not found: {talmud_path}")
        return []
    
    with open(talmud_path, 'r') as f:
        data = json.load(f)
    
    def find_rashbam_bb(node, path=[]):
        if isinstance(node, dict):
            if node.get("title") == "Rashbam on Bava Batra":
                return node
            for child in node.get("children", []):
                res = find_rashbam_bb(child, path + [node.get("title")])
                if res:
                    return res
        elif isinstance(node, list):
            for child in node:
                res = find_rashbam_bb(child, path)
                if res:
                    return res
        return None
    
    node = find_rashbam_bb(data)
    if not node:
        print("  Rashbam on Bava Batra not found in talmud.json")
        return []
    
    children = node.get("children", [])
    refs = [c.get("ref") for c in children if c.get("ref")]
    print(f"  Found {len(refs)} refs")
    print(f"  First 5: {refs[:5]}")
    print(f"  Last 5: {refs[-5:]}")
    return refs

def run(ref):
    print(f"\n  Fetching: {ref}")
    data = fetch(ref, before=0, after=2)
    pages = data["pages"]
    print(f"  main_page_index: {data['main_page_index']}")
    print(f"  Total pages: {len(pages)}")
    for i, p in enumerate(pages):
        marker = " <== MAIN" if i == data["main_page_index"] else ""
        print(f"  [{i}] {summarize(p)}{marker}")

if __name__ == "__main__":
    available_refs = check_talmud_refs()
    
    test_refs = [
        "Rashbam on Bava Batra 29a",
        "Rashbam on Bava Batra 29b",
        "Rashbam on Bava Batra 30a",
        "Rashbam on Bava Batra 30b",
    ]
    
    if available_refs:
        print(f"\n=== Using first few available refs from menu ===")
        test_refs = available_refs[:4]
    
    for ref in test_refs:
        print(f"\n{'='*60}")
        print(f"=== Testing: {ref}")
        try:
            run(ref)
        except requests.exceptions.HTTPError as e:
            print(f"  HTTP Error: {e}")
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

