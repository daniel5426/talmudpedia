from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from datetime import datetime
from bson import ObjectId

from ingestion.vector_store import VectorStore
from app.db.connection import MongoDatabase
from app.db.models.chat import Chat, Message
from app.db.models.sefaria import Text
from agent import agent as chat_agent
import agent as agent_module
from langchain_core.messages import HumanMessage, AIMessage

load_dotenv(Path(__file__).parent / ".env")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await MongoDatabase.connect()
    
    # Initialize VectorStore
    pinecone_key = os.getenv("PINECONE_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY")
    
    app.state.vector_store = None
    if pinecone_key and google_key:
        try:
            app.state.vector_store = VectorStore(pinecone_api_key=pinecone_key, google_api_key=google_key)
            agent_module.vector_store = app.state.vector_store  # Set the global vector_store in agent module
            print("VectorStore initialized successfully.")
        except Exception as e:
            print(f"Failed to initialize VectorStore: {e}")
    else:
        print("Warning: API keys missing. Vector search will not work.")
        
    yield
    
    # Shutdown
    await MongoDatabase.close()

app = FastAPI(title="Rabbinic AI API", version="0.1.0", lifespan=lifespan)

class ChatRequest(BaseModel):
    message: str
    chatId: Optional[str] = None

@app.get("/")
def read_root():
    return {"message": "Welcome to the Rabbinic AI API", "status": "active"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/search")
def search(q: str, limit: int = 10):
    if not app.state.vector_store:
        raise HTTPException(status_code=503, detail="Vector search service unavailable (missing configuration).")
    
    results = app.state.vector_store.search(q, limit=limit)
    return {"results": results}

# Chat Endpoints

@app.get("/chats", response_model_by_alias=False)
async def get_chats(limit: int = 20, cursor: Optional[str] = None):
    db = MongoDatabase.get_db()
    query: Dict[str, Any] = {}
    if cursor:
        try:
            cursor_time = datetime.fromisoformat(cursor)
            query["updated_at"] = {"$lt": cursor_time}
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid cursor value")
    db_cursor = db.chats.find(query).sort("updated_at", -1).limit(limit)
    chats = []
    last_timestamp: Optional[datetime] = None
    async for doc in db_cursor:
        chat = Chat(**doc)
        chat_dict = chat.model_dump(by_alias=False)
        chat_dict["id"] = str(chat.id)
        chats.append(chat_dict)
        last_timestamp = chat.updated_at
    next_cursor = last_timestamp.isoformat() if last_timestamp and len(chats) == limit else None
    return {"items": chats, "nextCursor": next_cursor}

@app.get("/chats/{chat_id}", response_model_by_alias=False)
async def get_chat_history(chat_id: str):
    db = MongoDatabase.get_db()
    try:
        doc = await db.chats.find_one({"_id": ObjectId(chat_id)})
        if doc:
            chat = Chat(**doc)
            chat_dict = chat.model_dump(by_alias=False)
            chat_dict["id"] = str(chat.id)
            return chat_dict
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="Chat not found")

@app.delete("/chats/{chat_id}")
async def delete_chat_endpoint(chat_id: str):
    print(f"Deleting chat with ID: {chat_id}")
    db = MongoDatabase.get_db()
    result = await db.chats.delete_one({"_id": ObjectId(chat_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"status": "deleted"}

def parse_ref(ref: str) -> Dict[str, Any]:
    """
    Parse a Sefaria-style reference into components.
    Examples:
      - "Genesis 1:1" -> {"index": "Genesis", "chapter": 1, "verse": 1}
      - "Genesis 1" -> {"index": "Genesis", "chapter": 1}
      - "Taanit 12a:12" -> {"index": "Taanit", "daf": "12a", "line": 12}
      - "Berakhot 2a" -> {"index": "Berakhot", "daf": "2a"}
    """
    # Pattern for Talmudic references (e.g., "Taanit 12a:12" or "Berakhot 2a")
    talmud_pattern = r"^(.+?)\s+(\d+)([ab])(?::(\d+))?$"
    match = re.match(talmud_pattern, ref, re.IGNORECASE)
    
    if match:
        index_title = match.group(1)
        daf_num = int(match.group(2))
        side = match.group(3).lower()
        line = int(match.group(4)) if match.group(4) else None
        daf = f"{daf_num}{side}"
        return {"index": index_title, "daf": daf, "daf_num": daf_num, "side": side, "line": line}
    
    # Pattern for biblical references (e.g., "Genesis 1:1" or "Genesis 1")
    biblical_pattern = r"^(.+?)\s+(\d+)(?::(\d+))?$"
    match = re.match(biblical_pattern, ref)
    
    if match:
        index_title = match.group(1)
        chapter = int(match.group(2))
        verse = int(match.group(3)) if match.group(3) else None
        return {"index": index_title, "chapter": chapter, "verse": verse}
    
    # If no pattern matches, assume it's just an index title
    return {"index": ref}

def parse_range_ref(ref: str) -> Optional[Dict[str, str]]:
    """
    Parse a range reference like "Taanit 4a:15-Taanit 4a:16".
    Returns a dict with start and end refs, or None if not a range.
    """
    # Check for hyphen
    if "-" not in ref:
        return None
    
    # Split by hyphen, handling potential spaces
    parts = ref.split("-")
    if len(parts) != 2:
        return None
        
    start_ref = parts[0].strip()
    end_ref = parts[1].strip()
    
    # Basic validation - ensure start ref is valid
    start_parsed = parse_ref(start_ref)
    if "index" not in start_parsed:
        return None
        
    # If end ref is just digits, it might be a shorthand (e.g. 15-16)
    # But for now we assume full refs as per user request, or at least parsable refs.
    # If the user passed "Taanit 4a:15-16", parse_ref("16") would return {"index": "16"} which is wrong.
    # We'll stick to the user's example "Taanit 4a:15-Taanit 4a:16" for now, 
    # but if end_ref looks like a number we could try to expand it. 
    # Let's keep it simple: assume both are full refs for now or that parse_ref handles them.
    
    return {"start": start_ref, "end": end_ref}

def get_adjacent_refs(ref: str, offset: int) -> Optional[str]:
    """
    Generate adjacent page reference given an offset.
    offset = -1 means previous page, +1 means next page, etc.
    
    Examples:
      - get_adjacent_refs("Genesis 1", 1) -> "Genesis 2"
      - get_adjacent_refs("Taanit 12a", 1) -> "Taanit 12b"
      - get_adjacent_refs("Taanit 12b", 1) -> "Taanit 13a"
    """
    if offset == 0:
        return ref
    
    parsed = parse_ref(ref)
    index_title = parsed["index"]
    
    # Handle Talmudic references (daf notation)
    if "daf" in parsed:
        daf_num = parsed["daf_num"]
        side = parsed["side"]
        
        # Convert to a linear index: 2a=0, 2b=1, 3a=2, 3b=3, etc.
        linear_index = (daf_num - 2) * 2 + (0 if side == 'a' else 1)
        new_linear_index = linear_index + offset
        
        if new_linear_index < 0:
            return None  # Before the start
        
        # Convert back to daf notation
        new_daf_num = (new_linear_index // 2) + 2
        new_side = 'a' if new_linear_index % 2 == 0 else 'b'
        
        return f"{index_title} {new_daf_num}{new_side}"
    
    # Handle biblical references (chapter notation)
    elif "chapter" in parsed and parsed["chapter"] is not None:
        new_chapter = parsed["chapter"] + offset
        
        if new_chapter < 1:
            return None  # Before chapter 1
        
        return f"{index_title} {new_chapter}"
    
    # Can't navigate from just an index title
    return None

@app.get("/texts/{ref}")
async def get_text(ref: str):
    db = MongoDatabase.get_db()
    # Try exact match first
    doc = await db.texts.find_one({"title": ref})
    if not doc:
        # Try case-insensitive match
        doc = await db.texts.find_one({"title": {"$regex": f"^{ref}$", "$options": "i"}})
    
    if doc:
        return Text(**doc)
    
    raise HTTPException(status_code=404, detail="Text not found")

@app.get("/api/source/{ref:path}")
async def get_source_text(ref: str, pages_before: int = 0, pages_after: int = 0):
    """
    Get the full text for a specific source reference.
    Returns the entire page/chapter with segments and highlights the specific reference.
    Supports references like "Genesis 1:1", "Genesis 1", "Taanit 12a:12", or just "Genesis".
    Also supports ranges like "Taanit 4a:15-Taanit 4a:16".
    
    Args:
        ref: The reference to fetch
        pages_before: Number of pages to load before the main page (default: 0)
        pages_after: Number of pages to load after the main page (default: 0)
    
    Returns:
        If pages_before or pages_after > 0: Multi-page response with pages array
        Otherwise: Single page response (legacy format)
    """
    db = MongoDatabase.get_db()
    
    # Check for range
    range_info = parse_range_ref(ref)
    primary_ref = ref
    range_start_parsed = None
    range_end_parsed = None
    
    if range_info:
        primary_ref = range_info["start"]
        range_start_parsed = parse_ref(range_info["start"])
        range_end_parsed = parse_ref(range_info["end"])
    
    async def fetch_page_data(page_ref: str, is_main_page: bool = False):
        """Helper to fetch data for a single page."""
        parsed = parse_ref(page_ref)
        index_title = parsed["index"]
        
        # Find the text document
        doc = await db.texts.find_one({"title": index_title})
        if not doc:
            doc = await db.texts.find_one({"title": {"$regex": f"^{index_title}$", "$options": "i"}})
        
        if not doc:
            return None
        
        chapter_data = doc.get("chapter", [])
        
        page_result = {
            "ref": page_ref,
            "segments": [],
            "highlight_index": None,
            "highlight_indices": []
        }
        
        # Helper to check if a segment index is within the requested range
        def is_in_range(current_idx: int, current_page_parsed: Dict[str, Any]) -> bool:
            if not range_info or not range_start_parsed or not range_end_parsed:
                return False
            
            # This is a simplified range check assuming we are on the correct page/chapter
            # It works well for ranges within a single page/chapter.
            # For cross-page ranges, we'd need to compare page indices too.
            
            # Check if we are on the start page
            is_start_page = False
            start_idx = -1
            
            if "daf" in current_page_parsed and "daf" in range_start_parsed:
                if current_page_parsed["daf"] == range_start_parsed["daf"]:
                    is_start_page = True
                    start_idx = range_start_parsed.get("line", 1) - 1
            elif "chapter" in current_page_parsed and "chapter" in range_start_parsed:
                if current_page_parsed["chapter"] == range_start_parsed["chapter"]:
                    is_start_page = True
                    start_idx = range_start_parsed.get("verse", 1) - 1
            
            # Check if we are on the end page
            is_end_page = False
            end_idx = 999999
            
            if "daf" in current_page_parsed and "daf" in range_end_parsed:
                if current_page_parsed["daf"] == range_end_parsed["daf"]:
                    is_end_page = True
                    end_idx = range_end_parsed.get("line", 999999) - 1
            elif "chapter" in current_page_parsed and "chapter" in range_end_parsed:
                if current_page_parsed["chapter"] == range_end_parsed["chapter"]:
                    is_end_page = True
                    end_idx = range_end_parsed.get("verse", 999999) - 1
            
            # Logic for same page range
            if is_start_page and is_end_page:
                return start_idx <= current_idx <= end_idx
            
            # Logic for multi-page range (not fully implemented yet, but this handles the start/end pages)
            # If we are on start page but not end page (range goes forward)
            if is_start_page and not is_end_page:
                 # We'd need to know if the end page is AFTER this page. 
                 # For now, let's just handle the start page part.
                 return current_idx >= start_idx
            
            # If we are on end page but not start page (range comes from before)
            if is_end_page and not is_start_page:
                return current_idx <= end_idx
                
            return False

        # Handle Talmudic references
        if "daf" in parsed:
            daf_num = parsed["daf_num"]
            side = parsed["side"]
            line = parsed.get("line")
            
            daf_index = (daf_num - 2) * 2 + (0 if side == 'a' else 1)
            
            if daf_index >= len(chapter_data):
                return None
            
            daf_content = chapter_data[daf_index]
            
            if isinstance(daf_content, list):
                page_result["segments"] = daf_content
                
                # Legacy single highlight
                if is_main_page and line is not None and not range_info:
                    line_index = line - 1
                    if line_index < len(daf_content):
                        page_result["highlight_index"] = line_index
                        page_result["highlight_indices"] = [line_index]
                
                # Range highlight
                if range_info:
                    for i in range(len(daf_content)):
                        if is_in_range(i, parsed):
                            page_result["highlight_indices"].append(i)
                    
                    # Set highlight_index to the first one for scrolling
                    if page_result["highlight_indices"]:
                        page_result["highlight_index"] = page_result["highlight_indices"][0]
                        
            else:
                page_result["segments"] = [daf_content]
                if is_main_page:
                    page_result["highlight_index"] = 0
                    page_result["highlight_indices"] = [0]
        
        # Handle biblical references
        elif "chapter" in parsed and parsed["chapter"] is not None:
            chapter_num = parsed["chapter"] - 1
            
            if chapter_num >= len(chapter_data):
                return None
            
            chapter_content = chapter_data[chapter_num]
            
            if isinstance(chapter_content, list):
                page_result["segments"] = chapter_content
                
                # Legacy single highlight
                if is_main_page and "verse" in parsed and parsed["verse"] is not None and not range_info:
                    verse_num = parsed["verse"] - 1
                    if verse_num < len(chapter_content):
                        page_result["highlight_index"] = verse_num
                        page_result["highlight_indices"] = [verse_num]
                
                # Range highlight
                if range_info:
                    for i in range(len(chapter_content)):
                        if is_in_range(i, parsed):
                            page_result["highlight_indices"].append(i)
                            
                    if page_result["highlight_indices"]:
                        page_result["highlight_index"] = page_result["highlight_indices"][0]

            else:
                page_result["segments"] = [chapter_content]
                if is_main_page:
                    page_result["highlight_index"] = 0
                    page_result["highlight_indices"] = [0]
        else:
            # Entire text
            for chapter in chapter_data:
                if isinstance(chapter, list):
                    page_result["segments"].extend(chapter)
                else:
                    page_result["segments"].append(chapter)
        
        return page_result, doc
    
    # Fetch main page
    main_page_data = await fetch_page_data(primary_ref, is_main_page=True)
    if main_page_data is None:
        raise HTTPException(status_code=404, detail=f"Reference '{ref}' not found")
    
    main_page, doc = main_page_data
    
    # If no multi-page request, return legacy format (extended with highlight_indices)
    if pages_before == 0 and pages_after == 0:
        return {
            "ref": ref,
            "index_title": doc.get("title"),
            "version_title": doc.get("versionTitle"),
            "language": doc.get("language"),
            "segments": main_page["segments"],
            "highlight_index": main_page["highlight_index"],
            "highlight_indices": main_page["highlight_indices"]
        }
    
    # Multi-page response
    pages = []
    
    # Load previous pages
    for i in range(pages_before, 0, -1):
        prev_ref = get_adjacent_refs(primary_ref, -i)
        if prev_ref:
            prev_data = await fetch_page_data(prev_ref)
            if prev_data:
                prev_page, _ = prev_data
                pages.append(prev_page)
    
    # Add main page
    main_page_index = len(pages)
    pages.append(main_page)
    
    # Load next pages
    for i in range(1, pages_after + 1):
        next_ref = get_adjacent_refs(primary_ref, i)
        if next_ref:
            next_data = await fetch_page_data(next_ref)
            if next_data:
                next_page, _ = next_data
                pages.append(next_page)
    
    return {
        "pages": pages,
        "main_page_index": main_page_index,
        "index_title": doc.get("title"),
        "version_title": doc.get("versionTitle"),
        "language": doc.get("language")
    }



@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    chat_id = request.chatId
    user_message = request.message
    db = MongoDatabase.get_db()
    
    # Create chat if not exists
    if not chat_id:
        chat = Chat(title=user_message[:30] + "...")
        result = await db.chats.insert_one(chat.model_dump(by_alias=True, exclude={"id"}))
        chat_id = str(result.inserted_id)
    
    # Save user message
    message = Message(role="user", content=user_message)
    await db.chats.update_one(
        {"_id": ObjectId(chat_id)},
        {
            "$push": {"messages": message.model_dump()},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    
    # Retrieve history for context
    chat_data = await db.chats.find_one({"_id": ObjectId(chat_id)})
    history_messages = []
    if chat_data:
        chat_obj = Chat(**chat_data)
        for msg in chat_obj.messages:
            if msg.role == "user":
                history_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                history_messages.append(AIMessage(content=msg.content))
    
    # Run Agent
    async def event_generator():
        full_response = ""
        collected_citations = []
        collected_reasoning = []
        
        # Initial reasoning step
        init_reasoning = {"step": "Analysis", "status": "active", "message": "Analyzing your question..."}
        collected_reasoning.append(init_reasoning)
        yield json.dumps({"type": "reasoning", "data": init_reasoning}) + "\n"
        
        inputs = {"messages": history_messages}
        
        async for event in chat_agent.astream_events(inputs, version="v1"):
            kind = event["event"]
            
            # Handle Retrieval Updates
            if kind == "on_chain_end" and event["name"] == "retrieve":
                data = event["data"].get("output")
                if data and "retrieved_docs" in data:
                    # Update Analysis to complete
                    analysis_complete = {"step": "Analysis", "status": "complete", "message": "Analysis complete."}
                    collected_reasoning.append(analysis_complete)
                    yield json.dumps({"type": "reasoning", "data": analysis_complete}) + "\n"
                    
                    # Start Retrieval
                    retrieval_active = {"step": "Retrieval", "status": "active", "message": "Searching Rabbinic texts..."}
                    collected_reasoning.append(retrieval_active)
                    yield json.dumps({"type": "reasoning", "data": retrieval_active}) + "\n"
                    
                    docs = data["retrieved_docs"]
                    for doc in docs:
                        meta = doc.get("metadata", {})
                        citation = {
                            "title": meta.get("ref", "Unknown Source"),
                            "url": f"https://talmudpedia.com/{meta.get('ref', '').replace(' ', '-')}", # Mock URL generation
                            "description": meta.get("text", "")[:100] + "..."
                        }
                        collected_citations.append(citation)
                        yield json.dumps({"type": "citation", "data": citation}) + "\n"
                    
                    # Complete Retrieval
                    retrieval_complete = {
                        "step": "Retrieval", 
                        "status": "complete", 
                        "message": f"Found {len(docs)} sources.",
                        "citations": collected_citations
                    }
                    collected_reasoning.append(retrieval_complete)
                    yield json.dumps({"type": "reasoning", "data": retrieval_complete}) + "\n"
                    
                    # Start Synthesis
                    synthesis_active = {"step": "Synthesis", "status": "active", "message": "Synthesizing answer..."}
                    collected_reasoning.append(synthesis_active)
                    yield json.dumps({"type": "reasoning", "data": synthesis_active}) + "\n"

            # Handle LLM Streaming
            elif kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    full_response += content
                    yield json.dumps({"type": "token", "content": content}) + "\n"

        # Finalize
        synthesis_complete = {"step": "Synthesis", "status": "complete", "message": "Answer generated."}
        collected_reasoning.append(synthesis_complete)
        yield json.dumps({"type": "reasoning", "data": synthesis_complete}) + "\n"

        # Save assistant message after streaming is done
        if full_response:
            asst_message = Message(
                role="assistant", 
                content=full_response,
                citations=collected_citations,
                reasoning_steps=collected_reasoning
            )
            await db.chats.update_one(
                {"_id": ObjectId(chat_id)},
                {
                    "$push": {"messages": asst_message.model_dump()},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            
    return StreamingResponse(event_generator(), media_type="application/x-ndjson", headers={"X-Chat-ID": chat_id})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
