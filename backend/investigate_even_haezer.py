import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import re
import json

sys.path.append(os.path.join(os.getcwd(), "backend"))

env_path = os.path.join(os.getcwd(), "backend", ".env")
load_dotenv(env_path)

class ReferenceNavigator:
    talmud_pattern = r"^(.+?)\s+(\d+)([ab])(?::(\d+))?$"
    biblical_pattern = r"^(.+?)\s+(\d+)(?::(\d+))?$"

    @classmethod
    def parse_ref(cls, ref: str):
        match = re.match(cls.talmud_pattern, ref, re.IGNORECASE)
        if match:
            index_title = match.group(1)
            daf_num = int(match.group(2))
            side = match.group(3).lower()
            line = int(match.group(4)) if match.group(4) else None
            daf = f"{daf_num}{side}"
            return {"index": index_title, "daf": daf, "daf_num": daf_num, "side": side, "line": line}
        match = re.match(cls.biblical_pattern, ref)
        if match:
            index_title = match.group(1)
            chapter = int(match.group(2))
            verse = int(match.group(3)) if match.group(3) else None
            return {"index": index_title, "chapter": chapter, "verse": verse}
        return {"index": ref}

async def investigate():
    mongo_uri = os.getenv("MONGO_URI") or "mongodb://localhost:27017"
    db_name = os.getenv("MONGO_DB_NAME", "sefaria")
    
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]
    
    index_title = "Shulchan Arukh, Even HaEzer"
    
    print(f"=== Investigating: {index_title} ===\n")
    
    all_docs = await db.texts.find({
        "title": {"$regex": f"^{index_title}$", "$options": "i"},
        "language": "he"
    }).to_list(length=None)
    
    print(f"Found {len(all_docs)} Hebrew document(s) for '{index_title}':\n")
    
    for i, doc in enumerate(all_docs):
        print(f"--- Document {i+1}: {doc.get('versionTitle', 'N/A')} (Priority: {doc.get('priority', 'N/A')}) ---")
        
        chapter_data = doc.get("chapter", [])
        print(f"Chapter data type: {type(chapter_data)}")
        
        if isinstance(chapter_data, dict):
            print(f"\nChapter data is a DICT with {len(chapter_data)} keys:")
            for key in chapter_data.keys():
                content = chapter_data[key]
                if isinstance(content, list):
                    print(f"  '{key}': LIST with {len(content)} elements")
                    if len(content) > 0:
                        preview = str(content[0])[:150] if content[0] else "EMPTY"
                        print(f"    First element preview: {preview}...")
                else:
                    print(f"  '{key}': {type(content).__name__}")
                    if content:
                        preview = str(content)[:150]
                        print(f"    Preview: {preview}...")
            
            print(f"\nChecking if 'default' key contains simanim:")
            if 'default' in chapter_data:
                default_content = chapter_data['default']
                if isinstance(default_content, list):
                    print(f"  'default' is a list with {len(default_content)} elements")
                    print(f"  This suggests simanim are stored as a flat list in 'default'")
                    print(f"  Testing simanim 1-10:")
                    for siman_num in range(1, 11):
                        siman_index = siman_num - 1
                        if siman_index < len(default_content):
                            content = default_content[siman_index]
                            if isinstance(content, list):
                                has_content = len(content) > 0
                            else:
                                has_content = bool(content)
                            status = "✓ HAS CONTENT" if has_content else "✗ EMPTY"
                            print(f"    Siman {siman_num} (index {siman_index}): {status}")
                        else:
                            print(f"    Siman {siman_num} (index {siman_index}): OUT OF BOUNDS (max: {len(default_content)-1})")
                elif isinstance(default_content, dict):
                    print(f"  'default' is a dict with keys: {list(default_content.keys())[:20]}")
                    print(f"  Checking if keys are siman numbers:")
                    for siman_num in range(1, 11):
                        key = str(siman_num)
                        if key in default_content:
                            content = default_content[key]
                            has_content = bool(content)
                            status = "✓ HAS CONTENT" if has_content else "✗ EMPTY"
                            print(f"    Siman {siman_num} (key '{key}'): {status}")
                        else:
                            print(f"    Siman {siman_num} (key '{key}'): NOT FOUND")
        elif isinstance(chapter_data, list):
            print(f"Chapter data is a LIST with {len(chapter_data)} elements")
        else:
            print(f"Chapter data is unexpected type: {type(chapter_data)}")
        
        print("\n" + "="*60 + "\n")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(investigate())
