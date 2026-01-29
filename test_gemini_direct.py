import asyncio
import os
import sys

# Ensure we can import from app
sys.path.append(os.getcwd())

from langchain_core.messages import HumanMessage
try:
    from app.agent.components.llm.gemini import GeminiLLM
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

async def test_gemini():
    print("Initializing GeminiLLM...")
    try:
        llm = GeminiLLM(model="gemini-2.0-flash") # Or "gemini-1.5-flash" / "gemini-pro"
        
        messages = [HumanMessage(content="Hello, say something short.")]
        
        print("Starting stream...")
        async for chunk in llm.stream(messages):
            print(f"Chunk received: {chunk.text if hasattr(chunk, 'text') else chunk}")
            
        print("Stream finished.")
        
    except Exception as e:
        print(f"Error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if not os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        print("WARNING: GOOGLE_API_KEY or GEMINI_API_KEY not set in env.")
        # Try to load from .env if possible, or assume user environment has it
    
    asyncio.run(test_gemini())
