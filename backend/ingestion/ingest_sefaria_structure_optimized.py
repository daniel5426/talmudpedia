import asyncio
import os
import sys
from typing import List
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Add current directory and backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

# Load env from backend/.env
env_path = os.path.join(os.getcwd(), "backend", ".env")
load_dotenv(env_path)

from ingestion.sefaria_client import SefariaClient

async def ingest_structure():
    print("🚀 Starting Optimized Sefaria Structure Ingestion...")
    
    # 1. Setup DB
    mongo_uri = os.getenv("MONGO_URI") or "mongodb://localhost:27017"
    db_name = os.getenv("MONGO_DB_NAME", "talmudpedia")
    
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]
    
    # Collections
    index_coll = db["index"]
    
    # 2. Setup Sefaria Client
    sefaria = SefariaClient()
    
    # 3. Fetch Table of Contents (single request!)
    print("Fetching table of contents from Sefaria...")
    loop = asyncio.get_event_loop()
    toc = await loop.run_in_executor(None, sefaria.get_table_of_contents)
    
    if not toc:
        print("❌ Failed to fetch table of contents. Aborting.")
        return
    
    print(f"✅ Received table of contents with {len(toc)} top-level categories.")
    
    # 4. Flatten and store
    # The TOC is hierarchical, we need to extract all books
    def extract_books(node, categories=[], he_categories=[]):
        """Recursively extract all books from the TOC tree."""
        books = []
        
        # If this node has a 'contents' key, it's a category
        if 'contents' in node:
            new_categories = categories + [node.get('category')]
            # Try to get Hebrew category, fallback to English if missing
            he_cat = node.get('heCategory', node.get('category'))
            new_he_categories = he_categories + [he_cat]
            
            for child in node['contents']:
                books.extend(extract_books(child, new_categories, new_he_categories))
        else:
            # It's a book
            book = {
                'title': node.get('title'),
                'heTitle': node.get('heTitle'),
                'categories': categories,
                'heCategories': he_categories,
                'primary_category': node.get('primary_category'),
                'enDesc': node.get('enDesc'),
                'heDesc': node.get('heDesc'),
            }
            books.append(book)
        
        return books
    
    all_books = []
    for category in toc:
        all_books.extend(extract_books(category))
    
    print(f"📚 Extracted {len(all_books)} books from TOC.")
    
    # 5. For each book, fetch shape data
    print("Fetching shape data for each book...")
    
    for i, book in enumerate(all_books):
        title = book['title']
        
        try:
            # Check if book exists
            existing_book = await index_coll.find_one({"title": title})
            if existing_book and "shape" in existing_book:
                book['shape'] = existing_book['shape']
            else:
                # Fetch shape
                shape_data = await loop.run_in_executor(None, sefaria.get_shape, title)
                book['shape'] = shape_data
            
            # Upsert into DB
            await index_coll.replace_one(
                {"title": title},
                book,
                upsert=True
            )
            
            if (i + 1) % 50 == 0:
                print(f"  Processed {i + 1}/{len(all_books)} books...")
                
        except Exception as e:
            print(f"⚠️  Error processing {title}: {e}")
            continue

    print("\n✅ Ingestion Complete.")
    
    # Verify counts
    count = await index_coll.count_documents({})
    print(f"Total Documents in 'index' collection: {count}")

if __name__ == "__main__":
    asyncio.run(ingest_structure())
