import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))
sys.path.append(os.path.join(os.getcwd(), "backend", "ingestion"))

load_dotenv(os.path.join(os.getcwd(), "backend", ".env"))

from ingestion.main import TextIngester

def test_ingestion():
    print("Starting Ingestion Test...")
    
    # Initialize Ingester
    try:
        ingester = TextIngester()
        print("TextIngester initialized.")
    except Exception as e:
        print(f"Failed to initialize TextIngester: {e}")
        return

    # Run ingestion for a small book with limit 1
    book = "Obadiah" 
    print(f"Ingesting {book} with limit=1...")
    
    try:
        # We use a small limit to avoid processing too much
        # We also need to make sure we don't actually write to Pinecone if we want to be safe, 
        # but the code writes to both. 
        # For this test, we accept writing 1 chunk to Pinecone and ES.
        ingester.ingest_index(book, limit=1, resume=False)
        print("Ingestion finished.")
    except Exception as e:
        print(f"Ingestion failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ingestion()
