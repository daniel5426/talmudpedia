import asyncio
import os
from datetime import datetime
from app.db.connection import MongoDatabase
from app.db.models.chat import Chat, Message, Citation, ReasoningStep
from app.db.models.sefaria import Text

async def verify_fixes():
    await MongoDatabase.connect()
    db = MongoDatabase.get_db()
    
    print("--- Verifying Message Persistence ---")
    # Create a chat
    chat = Chat(title="Verification Chat")
    result = await db.chats.insert_one(chat.model_dump(by_alias=True, exclude={"id"}))
    chat_id = result.inserted_id
    print(f"Created chat: {chat_id}")
    
    # Create a message with citations and reasoning
    citations = [
        Citation(title="Test Source", url="http://test.com", description="Test Description")
    ]
    reasoning = [
        ReasoningStep(step="Analysis", status="complete", message="Test Analysis")
    ]
    
    msg = Message(
        role="assistant", 
        content="Test Content", 
        citations=citations, 
        reasoning_steps=reasoning
    )
    
    # Update chat
    await db.chats.update_one(
        {"_id": chat_id},
        {"$push": {"messages": msg.model_dump()}}
    )
    
    # Retrieve and verify
    retrieved_chat_doc = await db.chats.find_one({"_id": chat_id})
    retrieved_chat = Chat(**retrieved_chat_doc)
    last_msg = retrieved_chat.messages[-1]
    
    if last_msg.citations and last_msg.citations[0].title == "Test Source":
        print("✅ Citations persisted correctly")
    else:
        print("❌ Citations failed")
        
    if last_msg.reasoning_steps and last_msg.reasoning_steps[0].step == "Analysis":
        print("✅ Reasoning steps persisted correctly")
    else:
        print("❌ Reasoning steps failed")
        
    # Clean up chat
    await db.chats.delete_one({"_id": chat_id})
    
    print("\n--- Verifying Text Retrieval ---")
    # Insert a dummy text
    text_ref = "Test Ref 1"
    text_doc = Text(
        title=text_ref,
        versionTitle="Test Version",
        versionSource="Test Source",
        language="en",
        chapter=["Test Content"]
    )
    await db.texts.insert_one(text_doc.model_dump(by_alias=True, exclude={"id"}))
    
    # Retrieve it
    found_doc = await db.texts.find_one({"title": text_ref})
    if found_doc and found_doc["title"] == text_ref:
        print("✅ Text retrieval works")
    else:
        print("❌ Text retrieval failed")
        
    # Clean up text
    await db.texts.delete_one({"title": text_ref})

    await MongoDatabase.close()

if __name__ == "__main__":
    asyncio.run(verify_fixes())
