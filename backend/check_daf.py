import asyncio
from app.db.connection import MongoDatabase
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path("backend/.env"))

async def check_daf():
    await MongoDatabase.connect()
    db = MongoDatabase.get_db()
    
    doc = await db.texts.find_one({"title": "Taanit"})
    
    if doc:
        chapter = doc.get('chapter', [])
        
        # 25b = (25-2)*2 + 1 = 47
        daf_index = (25 - 2) * 2 + 1
        
        print(f"Taanit 25b (index {daf_index}):")
        if daf_index < len(chapter):
            daf_content = chapter[daf_index]
            print(f"  Type: {type(daf_content)}")
            if isinstance(daf_content, list):
                print(f"  Length: {len(daf_content)} lines")
                if len(daf_content) > 0:
                    print(f"  First line: {daf_content[0][:100]}...")
            else:
                print(f"  Content: {str(daf_content)[:100]}...")
        else:
            print(f"  Index {daf_index} out of range (total: {len(chapter)})")
    
    await MongoDatabase.close()

if __name__ == "__main__":
    asyncio.run(check_daf())
