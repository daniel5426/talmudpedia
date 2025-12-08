
import asyncio
import os
import sys
from unittest.mock import MagicMock

sys.path.append(os.path.join(os.getcwd(), 'backend'))

# Mocks
sys.modules['app.agent'] = MagicMock()
sys.modules['app.agent.factory'] = MagicMock()
sys.modules['app.endpoints.agent'] = MagicMock()
sys.modules['vector_store'] = MagicMock()
sys.modules['app.agent.components'] = MagicMock()
sys.modules['app.agent.components.llm'] = MagicMock()
sys.modules['app.agent.components.llm.openai'] = MagicMock()

from app.db.connection import MongoDatabase
import app.endpoints.texts as texts_module

# Extract classes
ReferenceNavigator = texts_module.ReferenceNavigator

async def debug_ref_check():
    await MongoDatabase.connect()
    db = MongoDatabase.get_db()
    
    index_title = 'Siddur Sefard'
    ref = 'Siddur Sefard, Weekday Shacharit, Korbanot'
    
    # 1. Check Index Schema for node structure
    print(f'Fetching Index: {index_title}')
    index_doc = await db.index.find_one({'title': index_title})
    schema = index_doc.get('schema', {}) if index_doc else {}
    
    # Helper
    def find_node(node, key):
        if node.get("key") == key:
            return node
        for child in node.get("nodes", []):
            res = find_node(child, key)
            if res: return res
        return None
        
    ws_node = find_node(schema, "Weekday Shacharit")
    if ws_node:
        print("Found 'Weekday Shacharit' Node.")
        print(f"Children: {[c.get('key') for c in ws_node.get('nodes', [])]}")
        
        # Check if 'Korbanot' is a child
        if any(c.get("key") == "Korbanot" for c in ws_node.get("nodes", [])):
            print("'Korbanot' IS a child of 'Weekday Shacharit'.")
            
            # Check Document coverage
            print("Checking document coverage for ref...")
            doc = await texts_module.TextService._find_best_document(db, index_title, ref=ref, schema=schema)
            if doc:
                print(f"Document Found: {doc.get('versionTitle')}")
                print(f"SectionRef: {doc.get('sectionRef')}")
            else:
                print("Document NOT Found (404 Cause).")
                
                # Check candidates without schema validation
                print("Candidates available:")
                cand = await db.texts.find({"title": index_title, "language": "he"}).to_list(None)
                for c in cand:
                     print(f"- {c.get('versionTitle')} (Section: {c.get('sectionRef')})")
        else:
            print("'Korbanot' is NOT a child of 'Weekday Shacharit'.")
            
    else:
        print("Node 'Weekday Shacharit' not found.")

    await MongoDatabase.close()

if __name__ == '__main__':
    asyncio.run(debug_ref_check())
