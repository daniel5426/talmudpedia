import argparse
from pathlib import Path
from dotenv import load_dotenv
from sefaria_client import SefariaClient
from chunker import Chunker
from vector_store import VectorStore

load_dotenv(Path(__file__).parent.parent / ".env")

def main():
    parser = argparse.ArgumentParser(description="Ingest Sefaria texts into Pinecone.")
    parser.add_argument("--index", type=str, default="Taanit", help="Sefaria Index Title to ingest")
    parser.add_argument("--limit", type=int, default=999999, help="Limit number of segments to process")
    args = parser.parse_args()

    # Initialize components
    sefaria = SefariaClient()
    chunker = Chunker()
    
    import os
    pinecone_key = os.getenv("PINECONE_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY")
    
    if not pinecone_key or not google_key:
        print("Error: PINECONE_API_KEY and GOOGLE_API_KEY must be set in environment.")
        return

    vector_store = VectorStore(pinecone_api_key=pinecone_key, google_api_key=google_key)

    print(f"Starting ingestion for index: {args.index}")

    # 1. Get Index Metadata (for context)
    index_meta = sefaria.get_index(args.index)
    if not index_meta:
        print(f"Could not find index: {args.index}")
        return
    
    # 2. Get Shape to understand structure (simplified for this demo: assume we iterate by Daf/Segment)
    # For a real full ingest, we'd traverse the shape. 
    # For this demo, we will use a known range or just start at the beginning.
    
    # Let's fetch the first few segments of the book using the Text API which handles structure traversal if we use "context" or just specific refs.
    # A simple way to iterate is to start with "Berakhot 2a" and follow "next" pointers.
    
    current_ref = f"{args.index} 2a" # Starting point for Bavli
    count = 0
    
    while count < args.limit and current_ref:
        print(f"Processing {current_ref}...")
        
        # 3. Fetch Text
        text_data = sefaria.get_text(current_ref)
        if not text_data:
            break
            
        # The text API returns a list of segments if we ask for a section (like a Daf), 
        # or a single segment if we ask for a specific line.
        # "Berakhot 2a" usually returns the whole Daf or a list of segments.
        
        # We need to handle the response structure. 
        # If 'text' is a list, it means we got a section. We need to zip it with 'he' and refs.
        
        texts = text_data['versions'][0]['text']
        if isinstance(texts, str):
            texts = [texts] # Normalize to list
        
        # We need the specific refs for each segment. 
        # The API might give us a range. 
        # A better approach for precise segment iteration:
        # Use the 'ref' field from the response and if it's a section, iterate its sub-units.
        
        # For this MVP, let's assume we are getting a section (Daf) and we iterate its segments.
        # We need to construct the segment ref. 
        # The 'text' field is a list of strings (segments).
        
        # Actually, to get precise per-segment data including links, it is often better to 
        # iterate known segment refs if we have them, OR use the section response and map indices.
        
        # Let's try to get related links for the *Section* and then filter, 
        # OR get related links for each *Segment* individually.
        # Getting related for each segment is more precise but more API calls.
        # For "Limit 10", we can do per-segment.
        
        section_ref = text_data.get("ref")
        
        section_segments = []
        section_links = []
        for i, segment_text in enumerate(texts):
            if count >= args.limit:
                break
            segment_ref = f"{section_ref}:{i+1}"
            links = sefaria.get_related(segment_ref)
            segment_data_payload = {
                "ref": segment_ref,
                "text": segment_text,
                "index_title": args.index,
                "version": {"versionTitle": text_data.get("versionTitle", "primary")},
                "shape_path": [args.index, section_ref]
            }
            section_segments.append(segment_data_payload)
            section_links.append(links.get("links", []) if links else [])
            count += 1

        if section_segments:
            chunks = chunker.chunk_segments(section_segments, section_links)
            if chunks:
                vector_store.upsert_chunks(chunks)

        if count >= args.limit:
            break

        # Move to next section
        current_ref = text_data.get("next")

    print("Ingestion complete.")

if __name__ == "__main__":
    main()
