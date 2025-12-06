import asyncio
import os
import sys
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from ingestion.sefaria_client import SefariaClient

# Add current directory to path
sys.path.append(os.getcwd())

env_path = os.path.join(os.getcwd(), "backend", ".env")
load_dotenv(env_path)

async def main():
    print("Starting Sefaria Data Verification...")
    
    # 1. Check MongoDB Connection and Data
    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB_NAME", "talmudpedia") # Default or from env
    
    if not mongo_uri:
        print("⚠️  MONGO_URI not found in environment variables. Using default: mongodb://localhost:27017")
        mongo_uri = "mongodb://localhost:27017"

    print(f"Connecting to MongoDB at {mongo_uri} (DB: {db_name})...")
    
    try:
        client = AsyncIOMotorClient(mongo_uri)
        db = client[db_name]
        
        # Check collections
        collections = await db.list_collection_names()
        print(f"Found collections: {collections}")
        
        # Check Index collection
        index_count = 0
        if "index" in collections:
            index_count = await db["index"].count_documents({})
        elif "indexes" in collections:
            index_count = await db["indexes"].count_documents({})
            
        # Check Text collection
        text_count = 0
        if "text" in collections:
            text_count = await db["text"].count_documents({})
        elif "texts" in collections:
            text_count = await db["texts"].count_documents({})
            
        print(f"📊 Local Data Status:")
        print(f"   - Index Documents: {index_count}")
        print(f"   - Text Documents: {text_count}")
        
        if index_count == 0 or text_count == 0:
            print("⚠️  Data missing! You need to run the ingestion process.")
        else:
            print("✅ Data appears to be present.")
            
    except Exception as e:
        print(f"❌ Failed to connect to MongoDB: {e}")

    # 2. Check Sefaria API Connectivity
    print("\nChecking Sefaria API Connectivity...")
    client = SefariaClient()
    try:
        # Fetch a known index (e.g., "Genesis")
        index = client.get_index("Genesis")
        if index:
            print("✅ Successfully fetched 'Genesis' index from Sefaria API.")
            # print(f"   - Title: {index.get('title')}")
            # print(f"   - Categories: {index.get('categories')}")
        else:
            print("❌ Failed to fetch 'Genesis' index.")
    except Exception as e:
        print(f"❌ Error connecting to Sefaria API: {e}")

    # 3. Check for Tree Structure (Normalized/Expanded)
    # The user guide mentions a 'sefaria_tree.json' or a flattened table.
    # We check if such a file exists or if the DB has a 'tree' collection.
    
    print("\nChecking for Expanded Tree...")
    tree_file = "sefaria_tree.json"
    if os.path.exists(tree_file):
        print(f"✅ Found {tree_file} locally.")
    else:
        print(f"❌ {tree_file} not found.")
        
    # Check DB for tree collection
    tree_count = 0
    if "tree" in collections:
        tree_count = await db["tree"].count_documents({})
        print(f"✅ Found 'tree' collection with {tree_count} nodes.")
    else:
        print("❌ 'tree' collection not found in DB.")

    print("\nVerification Complete.")

if __name__ == "__main__":
    asyncio.run(main())
