import asyncio
import os
import sys
from fastapi import HTTPException

# Add the current directory to sys.path
sys.path.append(os.getcwd())
os.environ["OPENAI_API_KEY"] = "sk-proj-dummy-key-for-testing-imports"
os.environ["GOOGLE_API_KEY"] = "dummy-google-key"

from app.db.connection import MongoDatabase
from app.endpoints.texts import TextEndpoints

async def main():
    await MongoDatabase.connect()
    
    ref = "Sha'ar HaHakdamot"
    print(f"Testing get_source_text for ref: {ref}")
    
    try:
        result = await TextEndpoints.get_source_text(ref, pages_before=0, pages_after=2)
        print("Success!")
        print(f"Result keys: {result.keys()}")
        print(f"Number of pages: {len(result['pages'])}")
        for i, page in enumerate(result['pages']):
            print(f"Page {i} ref: {page['ref']}")
            print(f"Page {i} segments count: {len(page['segments'])}")
    except Exception as e:
        print(f"Failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
