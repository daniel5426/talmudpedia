
import asyncio
import sys
import os
from unittest.mock import MagicMock

# Add backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

# MOCK PROBLEM MODULES BEFORE IMPORTING
sys.modules["app.agent"] = MagicMock()
sys.modules["app.agent.factory"] = MagicMock()
sys.modules["app.endpoints.agent"] = MagicMock()

from app.endpoints.texts import TextEndpoints
from app.db.connection import MongoDatabase

async def test_ref(ref):
    print(f"\n--- Testing Ref: {ref} ---")
    try:
        result = await TextEndpoints.get_source_text(ref)
        print("Success!")
        print(f"Ref: {result['pages'][0]['ref']}")
        print(f"HeRef: {result['pages'][0].get('he_ref')}")
        print(f"Title: {result['index_title']}")
        print(f"HeTitle: {result['he_title']}")
        print(f"Can Load More: {result['can_load_more']}")
        
        segments = result['pages'][0]['segments']
        print(f"Segment Count: {len(segments)}")
        if segments:
            print(f"First Segment: {segments[0][:50]}...")
    except Exception as e:
        print(f"Error: {e}")

async def main():
    # Connect to DB
    await MongoDatabase.connect()
    db = MongoDatabase.get_db()
    index_coll = db.client.talmudpedia.index
    
    print("\n--- Diagnostic Check ---")
    
    # Check 'talmudpedia' DB
    print("\nChecking DB: talmudpedia")
    tp_db = db.client.talmudpedia
    tp_docs = await tp_db.index.find({"title": {"$regex": "Sefer Mitzvot Gadol", "$options": "i"}}).to_list(length=None)
    print(f"Found {len(tp_docs)} docs in talmudpedia.index matching 'Sefer Mitzvot Gadol'")
    for d in tp_docs:
        print(f" - ID: {d['_id']}, Title: {d.get('title')}, Keys: {list(d.keys())}")
        if "schema" in d:
             print("   ✅ HAS SCHEMA")
             # Print root node keys to verify structure
             if "nodes" in d["schema"]:
                 print(f"   Schema Nodes: {[n.get('key') for n in d['schema']['nodes']]}")
        else:
             print("   ❌ MISSING SCHEMA")

    # Check 'sefaria' DB
    print("\nChecking DB: sefaria")
    sef_db = db.client.sefaria
    sef_docs = await sef_db.index.find({"title": {"$regex": "Sefer Mitzvot Gadol", "$options": "i"}}).to_list(length=None)
    
    def print_schema_recursive(node, depth=0):
        indent = "  " * depth
        keys = list(node.keys())
        title_en = next((t["text"] for t in node.get("titles", []) if t.get("primary") and t.get("lang") == "en"), "No Title")
        print(f"{indent}- Key: {node.get('key')} | Title: {title_en} | Type: {node.get('nodeType', 'Unknown')}")
        if "nodes" in node:
            for child in node["nodes"]:
                print_schema_recursive(child, depth + 1)
                
    for d in sef_docs:
        print(f" - ID: {d['_id']}, Title: {d.get('title')}")
        if "schema" in d:
             print("   ✅ HAS SCHEMA. Structure:")
             print_schema_recursive(d["schema"], 1)
        else:
             print("   ❌ MISSING SCHEMA")


    # Test cases from user report
    refs_to_test = [
        "Sefer Mitzvot Gadol, Positive Commandments, Remazim",
        "Sefer Mitzvot Gadol, Introduction", # Hakdama
        "Sefer Mitzvot Gadol, Positive Commandments 1", # Mitzvot Aseh 1
    ]

    for ref in refs_to_test:
        await test_ref(ref)

if __name__ == "__main__":
    asyncio.run(main())
